"""
Strategy — edge calculation, trade signal generation, Kelly Criterion position sizing.
"""

from typing import Optional
from utils.logger import log
from config.settings import settings


class Strategy:
    """
    Determine whether to trade and how much, based on:
      - Edge = market_implied_yes_prob - forecast_yes_prob
      - Kelly Criterion for position sizing
    """

    def __init__(self):
        self.no_threshold = settings.NO_THRESHOLD
        self.edge_threshold = settings.EDGE_THRESHOLD
        self.kelly_factor = settings.KELLY_FACTOR
        self.take_profit_threshold = settings.TAKE_PROFIT_THRESHOLD

    def evaluate(
        self,
        market: dict,
        forecast_prob_yes: float,
        wallet_balance: float,
    ) -> Optional[dict]:
        """
        Evaluate a market for a potential trade.

        Args:
            market: Market data from scanner (with yes_price, no_price, etc.)
            forecast_prob_yes: Estimated probability the event occurs (from EdgeModel)
            wallet_balance: Current USDC balance

        Returns:
            Trade signal dict or None if no trade.
        """
        yes_price = market.get("yes_price")
        no_price = market.get("no_price")

        if yes_price is None or no_price is None:
            log.debug(f"[strategy] Skipping {market.get('city', '?')}: missing prices")
            return None

        # Market implied probability
        market_yes_prob = yes_price  # YES price ≈ implied YES probability
        market_no_prob = no_price    # NO price ≈ implied NO probability

        # Forecast probability
        forecast_no_prob = 1.0 - forecast_prob_yes

        # Edge: how much the market overestimates YES
        # Positive edge means market YES is overpriced → buy NO
        edge = market_yes_prob - forecast_prob_yes

        log.info(
            f"[strategy] {market.get('city', '?')}: "
            f"market_yes={market_yes_prob:.2%}, forecast_yes={forecast_prob_yes:.2%}, "
            f"edge={edge:.2%}, no_price={no_price:.4f}"
        )

        # ── Trade conditions ──
        # 1) NO probability must be above threshold (market strongly favors NO)
        if market_no_prob < self.no_threshold:
            log.debug(
                f"[strategy] SKIP {market.get('city')}: "
                f"NO prob {market_no_prob:.2%} < threshold {self.no_threshold:.2%}"
            )
            return None

        # 2) Edge must exceed threshold
        if edge < self.edge_threshold:
            log.debug(
                f"[strategy] SKIP {market.get('city')}: "
                f"edge {edge:.2%} < threshold {self.edge_threshold:.2%}"
            )
            return None

        # ── Position sizing with Kelly Criterion ──
        position_size = self._kelly_size(
            forecast_no_prob=forecast_no_prob,
            no_price=no_price,
            balance=wallet_balance,
        )

        if position_size <= 0:
            log.debug(f"[strategy] SKIP {market.get('city')}: Kelly size <= 0")
            return None

        signal = {
            "action": "BUY_NO",
            "market": market,
            "edge": round(edge, 4),
            "market_yes_prob": round(market_yes_prob, 4),
            "forecast_yes_prob": round(forecast_prob_yes, 4),
            "forecast_no_prob": round(forecast_no_prob, 4),
            "no_price": no_price,
            "position_size_usdc": round(position_size, 2),
            "kelly_raw": None,  # filled below
        }

        log.info(
            f"[strategy] ✅ SIGNAL: BUY NO on {market.get('city')} | "
            f"edge={edge:.2%} | size=${position_size:.2f}"
        )
        return signal

    def _kelly_size(
        self,
        forecast_no_prob: float,
        no_price: float,
        balance: float,
    ) -> float:
        """
        Kelly Criterion position sizing.

        f = (b*p - q) / b

        where:
          b = net odds = (1 / no_price) - 1  (payout per dollar risked)
          p = forecast probability of NO winning
          q = 1 - p
        """
        if no_price <= 0 or no_price >= 1:
            return 0.0

        b = (1.0 / no_price) - 1.0  # net odds
        p = forecast_no_prob
        q = 1.0 - p

        kelly_fraction = (b * p - q) / b if b > 0 else 0.0
        kelly_fraction = max(0.0, kelly_fraction)  # No negative sizing

        # Apply Kelly factor (fractional Kelly for safety)
        adjusted = kelly_fraction * self.kelly_factor
        position_size = adjusted * balance

        # Cap at 10% of balance as extra safety
        max_position = balance * 0.10
        position_size = min(position_size, max_position)

        log.debug(
            f"[strategy] Kelly: b={b:.3f}, p={p:.4f}, q={q:.4f}, "
            f"f_raw={kelly_fraction:.4f}, f_adj={adjusted:.4f}, "
            f"size=${position_size:.2f}"
        )

        return position_size

    def evaluate_take_profit(self, market: dict, position: dict) -> Optional[dict]:
        """
        Evaluate if an open NO position should be closed for profit.

        Args:
            market: The live market dictionary from the scanner
            position: The open position dictionary from the Wallet

        Returns:
            Trade signal dict for SELL_NO or None
        """
        no_price = market.get("no_price")
        if no_price is None:
            return None

        condition_id = market.get("condition_id")
        if not condition_id or condition_id.lower() != position.get("conditionId", "").lower():
            return None

        if position.get("outcome") != "No":
            return None

        if no_price >= self.take_profit_threshold:
            size_to_sell = float(position.get("size", 0.0))
            if size_to_sell <= 0:
                return None

            signal = {
                "action": "SELL_NO",
                "market": market,
                "no_price": no_price,
                "position_size_shares": size_to_sell, # Amount to sell is measured in shares
            }

            log.info(
                f"[strategy] 💰 TAKE PROFIT SIGNAL: SELL NO on {market.get('city')} | "
                f"Live Price={no_price:.4f} >= Threshold={self.take_profit_threshold:.4f} | Shares={size_to_sell:.4f}"
            )
            return signal
        
        return None
