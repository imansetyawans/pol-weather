# Polymarket Weather Bot --- Quant Prompt with NOAA Edge Detection

You are a senior quantitative developer specializing in prediction
markets, trading systems, and probabilistic modeling.

Your task is to design and implement a production-grade Python trading
bot that trades weather markets on Polymarket.

The bot focuses specifically on temperature markets where the event
question is:

"Highest temperature in `<city>`{=html} on `<date>`{=html}"

Example: https://polymarket.com/weather/temperature
Focusing on market highest temperature like: https://polymarket.com/event/highest-temperature-in-shanghai-on-march-19-2026

Reference documentation: https://docs.polymarket.com/
Reference documenation: "C:\Users\imanse067687\Documents\0. Projects\new-pro\agent-skills"

The system must be modular, reliable, and quant-driven.

------------------------------------------------------------------------

## Core Objective

Build a Python bot that trades the **NO outcome** in temperature markets
only when the market price deviates from real-world weather forecast
probabilities.

The bot should exploit mispricing between:

Polymarket implied probability\
vs\
NOAA forecast probability

------------------------------------------------------------------------

## Market Selection

The bot scans Polymarket every **1 hour**.

Filters:

1.  Category = Weather
2.  Market title contains **"Highest Temperature"**
3.  Market resolution date within:
    -   24 hours
    -   48 hours
4.  From filtered markets select:

Top **3 markets by trading volume**.

------------------------------------------------------------------------

## Weather Data Source

Primary source:

https://api.weather.gov/

Required data:

-   hourly forecast
-   daily high temperature forecast
-   probability distribution if available

Fallback providers:

-   OpenWeatherMap API
-   Meteostat API

------------------------------------------------------------------------

## Edge Detection Model

Example event:

Highest temperature in Shanghai exceeds **30°C**

Steps:

1.  Extract temperature threshold from market question
2.  Fetch NOAA hourly forecast
3.  Estimate probability that the temperature exceeds the threshold

Possible methods:

-   Monte Carlo simulation
-   Normal distribution estimation
-   Historical error correction

------------------------------------------------------------------------

## Expected Value Calculation

Market Implied Probability Example:

NO price = 0.96\
YES price = 0.04

Implied YES probability = **4%**

Edge formula:

Edge = Forecast Probability - Market Implied Probability

Example:

Forecast probability = 1%\
Market implied probability = 4%

Edge = **-3%**

Market overestimates the event likelihood → **Buy NO**

------------------------------------------------------------------------

## Trade Conditions

Trade only when:

-   NO probability \> **85%**
-   Edge \> configurable threshold

Example:

EDGE_THRESHOLD = **2%**

------------------------------------------------------------------------

## Position Sizing

Use **Kelly Criterion**

Kelly formula:

f = (bp - q) / b

Where:

b = odds\
p = forecast probability\
q = 1 - p

Position size:

Position Size = Kelly × KellyFactor

Default:

KellyFactor = **0.25**

Must be configurable.

------------------------------------------------------------------------

## Order Execution

Use **Polymarket CLOB API**.

Order type:

-   FAK (Fill and Kill)
-   Market

Trade side:

BUY

Outcome:

NO

The bot must **never buy the same outcome twice in the same market**.

------------------------------------------------------------------------

## Bot Loop

Every hour:

1.  Scan markets
2.  Filter weather markets
3.  Select top 3 by volume
4.  Fetch NOAA forecast
5.  Estimate probability
6.  Calculate edge
7.  Execute trade if conditions met
8.  Update dashboard

------------------------------------------------------------------------

## Wallet Requirements

Wallet type:

EOA (Externally Owned Account)

Functions:

-   check balance
-   place orders
-   check positions
-   auto redeem winnings after market resolution

------------------------------------------------------------------------

## RPC Management

Environment variables:

RPC_URL\
RPC_FALLBACK_URL

If primary RPC fails → switch automatically to fallback.

------------------------------------------------------------------------

## Dashboard (TUI)

Use:

-   textual
-   rich

Dashboard sections:

### Markets Table

-   Market
-   City
-   Threshold temperature
-   Resolution time
-   Volume
-   YES price
-   NO price
-   Forecast probability
-   Market probability
-   Edge %

### Positions

-   Market
-   Entry price
-   Size
-   Unrealized PnL

### Bot Status

-   Last scan time
-   RPC status
-   Active markets
-   Wallet balance

### Logs

-   Trades
-   Forecast data
-   Errors
-   Strategy decisions

------------------------------------------------------------------------

## Project Structure

polymarket-weather-bot/

bot/ - market_scanner.py - weather_fetcher.py - edge_model.py -
strategy.py - trader.py - wallet.py - rpc_manager.py

dashboard/ - tui.py

config/ - settings.py

utils/ - logger.py - helpers.py

main.py\
requirements.txt\
.env.example\
README.md

------------------------------------------------------------------------

## Environment Configuration

PRIVATE_KEY=\
RPC_URL=\
RPC_FALLBACK_URL=

SCAN_INTERVAL=3600\
TOP_MARKETS=3

NO_THRESHOLD=0.85\
EDGE_THRESHOLD=0.02

KELLY_FACTOR=0.25

NOAA_API=https://api.weather.gov

------------------------------------------------------------------------

## Failsafe Requirements

The bot must include:

-   retry logic
-   RPC fallback
-   rate limit handling
-   duplicate trade prevention
-   API timeout protection

------------------------------------------------------------------------

## Output Requirements

Generate:

1.  Complete Python implementation
2.  Modular architecture
3.  requirements.txt
4.  .env.example
5.  README.md with setup instructions
6.  Clear code comments

------------------------------------------------------------------------

## Priorities

-   Reliability
-   Edge-based trading
-   Low latency
-   Clean architecture
-   Quantitative decision making
