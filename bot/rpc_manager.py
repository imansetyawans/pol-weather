"""
RPC Manager — Web3 provider with automatic failover.
"""

from web3 import Web3
from utils.logger import log
from config.settings import settings


class RPCManager:
    """Manage Web3 connections with primary + fallback RPC."""

    def __init__(self):
        self.primary_url = settings.RPC_URL
        self.fallback_url = settings.RPC_FALLBACK_URL
        self._web3: Web3 | None = None
        self._using_fallback = False

    @property
    def w3(self) -> Web3:
        if self._web3 is None or not self._is_connected():
            self._connect()
        return self._web3  # type: ignore

    def _is_connected(self) -> bool:
        try:
            return self._web3 is not None and self._web3.is_connected()
        except Exception:
            return False

    def _connect(self):
        """Try primary, fall back to secondary."""
        # Try primary
        if not self._using_fallback:
            try:
                self._web3 = Web3(Web3.HTTPProvider(self.primary_url, request_kwargs={"timeout": 10}))
                if self._web3.is_connected():
                    log.info(f"[rpc] Connected to primary RPC: {self.primary_url[:40]}...")
                    return
            except Exception as exc:
                log.warning(f"[rpc] Primary RPC failed: {exc}")

        # Try fallback
        try:
            self._web3 = Web3(Web3.HTTPProvider(self.fallback_url, request_kwargs={"timeout": 10}))
            if self._web3.is_connected():
                self._using_fallback = True
                log.info(f"[rpc] Connected to fallback RPC: {self.fallback_url[:40]}...")
                return
        except Exception as exc:
            log.error(f"[rpc] Fallback RPC also failed: {exc}")

        log.error("[rpc] ⚠ No RPC connection available")

    def get_status(self) -> dict:
        """Return current connection status for dashboard."""
        connected = self._is_connected()
        return {
            "connected": connected,
            "provider": "fallback" if self._using_fallback else "primary",
            "url": self.fallback_url if self._using_fallback else self.primary_url,
            "block": self._web3.eth.block_number if connected and self._web3 else None,
        }

    def reset_to_primary(self):
        """Attempt to reconnect to primary RPC."""
        self._using_fallback = False
        self._web3 = None
        self._connect()
