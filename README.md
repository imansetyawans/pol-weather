# 🌤️ Polymarket Weather Bot

**Quantitative trading bot** that trades **NO** on weather temperature markets on Polymarket, exploiting mispricing between market prices and real-world weather forecast probabilities.

---

## How It Works

Every hour the bot:
1. **Scans** Polymarket for active "Highest Temperature" markets (resolving within 24-48h)
2. **Fetches** weather forecasts from NOAA (US) / OpenWeatherMap (international)
3. **Calculates edge** between market implied probability and forecast probability using Monte Carlo + Normal Distribution
4. **Executes trades** (BUY NO) when edge exceeds threshold, sized by Kelly Criterion
5. **Displays** everything in a live TUI dashboard

---

## Architecture

```
polymarket-weather-bot/
├── main.py                  # Entry point & bot orchestrator
├── config/
│   └── settings.py          # Centralized .env config
├── bot/
│   ├── market_scanner.py    # Gamma API market discovery
│   ├── weather_fetcher.py   # NOAA + OpenWeatherMap forecasts
│   ├── edge_model.py        # Probability estimation (Normal + MC)
│   ├── strategy.py          # Edge calc + Kelly Criterion sizing
│   ├── trader.py            # CLOB order execution + duplicate prevention
│   ├── wallet.py            # Balance + positions
│   └── rpc_manager.py       # Web3 RPC with failover
├── dashboard/
│   └── tui.py               # Textual TUI dashboard
├── utils/
│   ├── logger.py            # Rich logging + file rotation
│   └── helpers.py           # Retry, rate limit, parsing
├── .env.example             # Environment template
└── requirements.txt         # Dependencies
```

---

## Setup

### 1. Clone & Install

```bash
cd polymarket-weather-bot
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your values:

| Variable | Required | Description |
|----------|----------|-------------|
| `PRIVATE_KEY` | ✅ | Polygon wallet private key |
| `FUNDER_ADDRESS` | ✅ | Wallet address (find at polymarket.com/settings) |
| `RPC_URL` | ✅ | Polygon RPC endpoint |
| `SIGNATURE_TYPE` | ✅ | `0`=EOA, `1`=POLY_PROXY, `2`=GNOSIS_SAFE |
| `OPENWEATHERMAP_API_KEY` | ❌ | For international cities (free tier works) |
| `DRY_RUN` | — | `true` (default) = no real trades |

### 3. Run

```bash
# TUI Dashboard (default — dry run)
python main.py

# Headless single scan
python main.py --headless

# Live trading (⚠️ real money)
python main.py --live
```

---

## Strategy Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `NO_THRESHOLD` | 0.85 | Minimum NO probability to consider a trade |
| `EDGE_THRESHOLD` | 0.02 | Minimum edge (2%) to trigger a trade |
| `KELLY_FACTOR` | 0.25 | Fractional Kelly (25% of full Kelly) |
| `SCAN_INTERVAL` | 3600 | Seconds between scans (1 hour) |
| `TOP_MARKETS` | 3 | Number of top markets to evaluate |

---

## Edge Detection

```
Edge = Market Implied YES Prob − Forecast YES Prob

If Edge > 2%:  Market overestimates temperature event → BUY NO
```

**Probability estimation** uses:
- **Normal distribution**: P(temp > threshold) = 1 − Φ((threshold − forecast) / σ)
- **Monte Carlo**: 10,000 samples from N(forecast, σ²), count fraction exceeding threshold
- **Combined**: 60% Normal + 40% Monte Carlo

---

## ⚠️ Disclaimer

This bot trades with real money on Polymarket. Always test with `DRY_RUN=true` first. Use at your own risk.
