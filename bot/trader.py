"""
Trader — Polymarket CLOB order execution, duplicate prevention, auto-redeem.
"""

import json
import os
import time
from typing import Optional
from utils.logger import log
from utils.helpers import retry_with_backoff
from config.settings import settings


class Trader:
    """
    Handle order placement on Polymarket CLOB.
    Uses py-clob-client for authentication and order submission.
    Tracks traded markets to prevent duplicates.
    """

    def __init__(self):
        self.dry_run = settings.DRY_RUN
        self._clob_client = None
        self._traded_markets: set[str] = set()
        self._trade_history: list[dict] = []
        self._load_traded_markets()

    def _init_client(self):
        """Initialize the py-clob-client with L1→L2 auth flow."""
        if self._clob_client is not None:
            return

        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import OrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY

            pk = settings.PRIVATE_KEY
            if not pk:
                log.error("[trader] PRIVATE_KEY not set — cannot initialize trading client")
                return

            # Step 1: Create temp client for L1 auth → derive API credentials
            temp_client = ClobClient(
                settings.CLOB_HOST,
                key=pk,
                chain_id=settings.CHAIN_ID,
            )
            api_creds = temp_client.create_or_derive_api_creds()
            log.info("[trader] Derived API credentials via L1 auth")

            # Step 2: Create full trading client with L2 auth
            self._clob_client = ClobClient(
                settings.CLOB_HOST,
                key=pk,
                chain_id=settings.CHAIN_ID,
                creds=api_creds,
                signature_type=settings.SIGNATURE_TYPE,
                funder=settings.FUNDER_ADDRESS,
            )
            log.info("[trader] Trading client initialized successfully")

        except ImportError:
            log.error("[trader] py-clob-client not installed. Run: pip install py-clob-client")
        except Exception as exc:
            log.error(f"[trader] Failed to initialize CLOB client: {exc}")

    def execute_trade(self, signal: dict) -> Optional[dict]:
        """
        Execute a trade based on a strategy signal.

        Args:
            signal: Trade signal from Strategy.evaluate()

        Returns:
            Trade result dict or None if failed/skipped.
        """
        market = signal.get("market", {})
        condition_id = market.get("condition_id", "")
        no_token_id = market.get("no_token_id")
        no_price = signal.get("no_price", 0)
        position_size = signal.get("position_size_usdc", 0)
        city = market.get("city", "unknown")

        # ── Duplicate check ──
        if condition_id in self._traded_markets:
            log.warning(f"[trader] SKIP: Already traded market {city} ({condition_id[:12]}...)")
            return None

        if not no_token_id:
            log.error(f"[trader] SKIP: No token ID missing for {city}")
            return None

        if position_size <= 0:
            log.warning(f"[trader] SKIP: Position size is 0 for {city}")
            return None

        # ── Dry run mode ──
        if self.dry_run:
            result = {
                "status": "dry_run",
                "city": city,
                "side": "BUY_NO",
                "amount": position_size,
                "price": no_price,
                "token_id": no_token_id[:16] + "...",
                "condition_id": condition_id[:16] + "...",
                "edge": signal.get("edge", 0),
                "timestamp": time.time(),
            }
            log.info(
                f"[trader] 🔸 DRY RUN: Would BUY NO on {city} | "
                f"${position_size:.2f} @ {no_price:.4f} | edge={signal.get('edge', 0):.2%}"
            )
            self._traded_markets.add(condition_id)
            self._trade_history.append(result)
            self._save_traded_markets()
            return result

        # ── Live execution ──
        self._init_client()
        if self._clob_client is None:
            log.error("[trader] Cannot execute: CLOB client not initialized")
            return None

        return self._place_order(signal)

    @retry_with_backoff(max_retries=2, exceptions=(Exception,))
    def _place_order(self, signal: dict) -> Optional[dict]:
        """Place a FAK BUY NO order via the CLOB API."""
        try:
            from py_clob_client.clob_types import OrderArgs, OrderType, MarketOrderArgs, PartialCreateOrderOptions
            from py_clob_client.order_builder.constants import BUY

            market = signal["market"]
            no_token_id = market["no_token_id"]
            no_price = signal["no_price"]
            amount = signal["position_size_usdc"]
            neg_risk = market.get("neg_risk", False)
            tick_size = market.get("tick_size", "0.01")
            city = market.get("city", "unknown")
            condition_id = market.get("condition_id", "")

            log.info(
                f"[trader] 🔶 Placing FAK BUY NO on {city}: "
                f"${amount:.2f} @ {no_price:.4f}"
            )

            # Add a small slippage buffer to the worst-case limit price
            # Polymarket FAK orders require a limit price; if set exactly to current mid, it won't fill.
            worst_price = round(min(0.99, no_price + 0.02), 3)

            # Create and post market order (FAK)
            order_args = MarketOrderArgs(
                token_id=no_token_id,
                side=BUY,
                amount=amount,
                price=worst_price,
            )
            opts = PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk)
            order = self._clob_client.create_market_order(
                order_args,
                options=opts,
            )
            response = self._clob_client.post_order(order, OrderType.FAK)

            result = {
                "status": "submitted",
                "order_id": response.get("orderID", ""),
                "insert_status": response.get("status", ""),
                "city": city,
                "side": "BUY_NO",
                "amount": amount,
                "price": no_price,
                "token_id": no_token_id[:16] + "...",
                "condition_id": condition_id[:16] + "...",
                "edge": signal.get("edge", 0),
                "timestamp": time.time(),
            }

            log.info(
                f"[trader] ✅ Order submitted for {city}: "
                f"orderID={result['order_id']}, status={result['insert_status']}"
            )

            self._traded_markets.add(condition_id)
            self._trade_history.append(result)
            self._save_traded_markets()
            return result

        except Exception as exc:
            err_msg = str(exc)
            if "FAK" in err_msg or "kill" in err_msg.lower() or "not filled" in err_msg.lower():
                log.warning(f"[trader] FAK order was killed (no matching liquidity at price): {err_msg}")
                return None
            else:
                log.error(f"[trader] Order placement failed: {exc}")
                raise

    # ── Traded markets persistence ──

    def _load_traded_markets(self):
        """Load previously traded market IDs from file."""
        path = settings.TRADED_MARKETS_FILE
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                self._traded_markets = set(data.get("markets", []))
                log.info(f"[trader] Loaded {len(self._traded_markets)} traded markets from file")
            except Exception as exc:
                log.warning(f"[trader] Failed to load traded markets: {exc}")

    def _save_traded_markets(self):
        """Persist traded market IDs to file."""
        try:
            with open(settings.TRADED_MARKETS_FILE, "w") as f:
                json.dump({"markets": list(self._traded_markets)}, f, indent=2)
        except Exception as exc:
            log.warning(f"[trader] Failed to save traded markets: {exc}")

    def has_traded(self, condition_id: str) -> bool:
        """Check if a market has already been traded."""
        return condition_id in self._traded_markets

    def get_trade_history(self) -> list[dict]:
        """Return list of all trades executed in this session."""
        return self._trade_history

    def reset_traded_markets(self):
        """Clear the traded markets list (for new day)."""
        self._traded_markets.clear()
        self._save_traded_markets()
        log.info("[trader] Reset traded markets list")
