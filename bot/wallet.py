"""
Wallet — balance checks, position queries, and auto-redeem functionality.
"""

import json
import requests
from typing import Optional
from utils.logger import log
from utils.helpers import retry_with_backoff
from config.settings import settings
from bot.rpc_manager import RPCManager


# Minimal USDC ERC-20 ABI (balanceOf only)
USDC_ABI = json.loads('[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],'
                       '"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],'
                       '"type":"function"}]')


class Wallet:
    """Interface for wallet balance, positions, and redemption."""

    def __init__(self, rpc_manager: RPCManager):
        self.rpc = rpc_manager
        self.address = settings.FUNDER_ADDRESS
        self._balance_cache: Optional[float] = None

    @retry_with_backoff(max_retries=2, exceptions=(Exception,))
    def get_usdc_balance(self) -> float:
        """Get USDC.e balance on Polygon (in human-readable units, 6 decimals)."""
        try:
            w3 = self.rpc.w3
            usdc = w3.eth.contract(
                address=w3.to_checksum_address(settings.USDC_ADDRESS),
                abi=USDC_ABI,
            )
            raw_balance = usdc.functions.balanceOf(
                w3.to_checksum_address(self.address)
            ).call()
            balance = raw_balance / 1e6  # USDC has 6 decimals
            self._balance_cache = balance
            return balance
        except Exception as exc:
            log.error(f"[wallet] Failed to fetch USDC balance: {exc}")
            if self._balance_cache is not None:
                return self._balance_cache
            raise

    @retry_with_backoff(max_retries=2, exceptions=(Exception,))
    def get_positions(self) -> list[dict]:
        """Fetch open positions from the Polymarket Data API."""
        try:
            url = f"{settings.DATA_HOST}/positions"
            params = {"user": self.address, "sizeThreshold": "0.01"}
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            positions = resp.json()
            return positions if isinstance(positions, list) else []
        except Exception as exc:
            log.error(f"[wallet] Failed to fetch positions: {exc}")
            return []

    def get_status(self) -> dict:
        """Return wallet summary for dashboard."""
        try:
            balance = self.get_usdc_balance()
        except Exception:
            balance = self._balance_cache or 0.0

        positions = self.get_positions()
        return {
            "address": self.address,
            "balance_usdc": round(balance, 2),
            "open_positions": len(positions),
            "positions": positions,
        }
