"""
Centralized configuration — loads all settings from .env with sensible defaults.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Bot-wide configuration singleton."""

    # ── Wallet & RPC ──
    PRIVATE_KEY: str = os.getenv("PRIVATE_KEY", "")
    FUNDER_ADDRESS: str = os.getenv("FUNDER_ADDRESS", "")
    RPC_URL: str = os.getenv("RPC_URL", "https://polygon-rpc.com")
    RPC_FALLBACK_URL: str = os.getenv("RPC_FALLBACK_URL", "https://rpc-mainnet.matic.quiknode.pro")
    SIGNATURE_TYPE: int = int(os.getenv("SIGNATURE_TYPE", "2"))

    # ── Polymarket ──
    CLOB_HOST: str = "https://clob.polymarket.com"
    GAMMA_HOST: str = "https://gamma-api.polymarket.com"
    DATA_HOST: str = "https://data-api.polymarket.com"
    CHAIN_ID: int = 137

    # ── Bot loop ──
    SCAN_INTERVAL: int = int(os.getenv("SCAN_INTERVAL", "3600"))
    TOP_MARKETS: int = int(os.getenv("TOP_MARKETS", "3"))
    DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"

    MIN_EDGE: float = float(os.getenv("MIN_EDGE", "0.05"))
    NO_THRESHOLD: float = float(os.getenv("NO_THRESHOLD", "0.90"))
    EDGE_THRESHOLD: float = float(os.getenv("EDGE_THRESHOLD", "0.05"))
    KELLY_FACTOR: float = float(os.getenv("KELLY_FACTOR", "0.25"))
    TAKE_PROFIT_THRESHOLD: float = float(os.getenv("TAKE_PROFIT_THRESHOLD", "0.99"))

    # ── Weather APIs ──
    NOAA_API: str = os.getenv("NOAA_API", "https://api.weather.gov")
    OPENWEATHERMAP_API_KEY: str = os.getenv("OPENWEATHERMAP_API_KEY", "")

    # ── Logging ──
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "bot.log")

    # ── Contracts (Polygon) ──
    USDC_ADDRESS: str = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    CTF_ADDRESS: str = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
    CTF_EXCHANGE: str = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
    NEG_RISK_CTF_EXCHANGE: str = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
    NEG_RISK_ADAPTER: str = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"

    # ── Traded markets persistence ──
    TRADED_MARKETS_FILE: str = os.getenv("TRADED_MARKETS_FILE", "traded_markets.json")


settings = Settings()
