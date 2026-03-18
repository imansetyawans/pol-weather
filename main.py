"""
Polymarket Weather Bot — Main Entry Point

Orchestrates the hourly bot loop:
  Scan markets → Fetch forecasts → Calculate edge → Execute trades → Update dashboard
"""

import asyncio
import argparse
import signal
import sys
import time
from datetime import datetime, timezone

from config.settings import settings
from utils.logger import log
from bot.rpc_manager import RPCManager
from bot.wallet import Wallet
from bot.market_scanner import MarketScanner
from bot.weather_fetcher import WeatherFetcher
from bot.edge_model import EdgeModel
from bot.strategy import Strategy
from bot.trader import Trader
from dashboard.tui import WeatherBotApp


class WeatherBot:
    """Main bot orchestrator — wires all modules together."""

    def __init__(self):
        self.rpc = RPCManager()
        self.wallet = Wallet(self.rpc)
        self.scanner = MarketScanner()
        self.weather = WeatherFetcher()
        self.edge_model = EdgeModel()
        self.strategy = Strategy()
        self.trader = Trader()

        self.app: WeatherBotApp | None = None
        self._running = False
        self._last_scan_time: str = "Never"
        self._enriched_markets: list[dict] = []

    async def run_with_tui(self):
        """Launch the TUI and run the bot loop concurrently."""
        self.app = WeatherBotApp()
        self._running = True

        # Start the bot loop as a background worker inside the app
        self.app.call_later(self._start_bot_worker)

        # Run the TUI (blocking)
        await self.app.run_async()

    def _start_bot_worker(self):
        """Schedule the bot loop as a Textual timer."""
        # Run immediately on startup, then every SCAN_INTERVAL
        self.app.set_timer(1, self._run_scan_cycle)
        self.app.set_interval(settings.SCAN_INTERVAL, self._run_scan_cycle)

    async def _run_scan_cycle(self):
        """Execute one full scan cycle."""
        try:
            self._log("━" * 50)
            self._log("🔄 Starting scan cycle...", "bold cyan")

            # ── 1. Get wallet status ──
            try:
                balance = self.wallet.get_usdc_balance()
                positions = self.wallet.get_positions()
                self.trader.sync_live_positions(positions)
            except Exception as e:
                self._log(f"⚠ Could not fetch live positions/balance: {e}", "yellow")
                balance = 0.0
            self._log(f"💰 Wallet balance: ${balance:.2f} USDC")

            # ── 2. Scan markets ──
            self._log("📡 Scanning Polymarket for weather markets...")
            markets = await asyncio.to_thread(self.scanner.scan)
            self._log(f"📊 Found {len(markets)} qualifying markets")

            if not markets:
                self._log("⚠ No temperature markets found in 24-48h window", "yellow")
                self._update_dashboard(balance, [], [])
                return

            # ── 3. Fetch forecasts + calculate edge for each market ──
            enriched = []
            for market in markets:
                city = market.get("city")
                if not city:
                    self._log(f"⚠ Skipping market with no city: {market.get('question', '?')}", "yellow")
                    continue

                # Fetch weather forecast
                self._log(f"🌤️  Fetching forecast for {city}...")
                forecast = await asyncio.to_thread(self.weather.fetch_forecast, city)

                if not forecast:
                    self._log(f"❌ No forecast available for {city}", "red")
                    continue

                market["forecast_high_c"] = forecast["forecast_high_c"]
                market["forecast_high_f"] = forecast["forecast_high_f"]
                market["forecast_source"] = forecast["source"]

                # Calculate edge
                threshold_c = market.get("threshold_c")
                if threshold_c is None:
                    self._log(f"⚠ No temperature threshold for {city}", "yellow")
                    continue

                prob_result = self.edge_model.estimate_with_hourly_data(
                    hourly_temps_c=forecast.get("hourly_temps_c", []),
                    threshold_c=threshold_c,
                    uncertainty_c=forecast.get("uncertainty_c", 2.0),
                )

                forecast_prob_yes = prob_result["prob_exceeds"]
                market["forecast_prob_yes"] = forecast_prob_yes
                market["edge"] = (market.get("yes_price", 0) or 0) - forecast_prob_yes

                self._log(
                    f"  📐 {city}: forecast={forecast['forecast_high_c']}°C, "
                    f"threshold={threshold_c}°C, P(exceed)={forecast_prob_yes:.2%}, "
                    f"edge={market['edge']:+.2%}"
                )

                # ── 4. Evaluate strategy ──
                signal = self.strategy.evaluate(market, forecast_prob_yes, balance)

                if signal:
                    # ── 5. Execute trade ──
                    self._log(f"🎯 Trade signal for {city}! Executing...", "bold green")
                    result = await asyncio.to_thread(self.trader.execute_trade, signal)
                    if result:
                        self._log(
                            f"✅ Trade {'(DRY RUN) ' if result.get('status') == 'dry_run' else ''}"
                            f"executed: BUY NO on {city} | ${result.get('amount', 0):.2f}",
                            "green",
                        )
                    else:
                        self._log(f"⚠ Trade skipped/failed for {city}", "yellow")
                else:
                    self._log(f"  ❌ No trade signal for {city}")

                enriched.append(market)

            # ── 6. Update dashboard ──
            self._enriched_markets = enriched
            self._last_scan_time = datetime.now().strftime("%H:%M:%S")
            self._update_dashboard(balance, enriched, self.trader.get_trade_history())
            self._log(f"✅ Scan cycle complete. Next scan in {settings.SCAN_INTERVAL}s", "bold green")

        except Exception as exc:
            self._log(f"❌ Scan cycle error: {exc}", "bold red")
            log.exception(f"Scan cycle failed: {exc}")

    def _update_dashboard(self, balance: float, markets: list, trades: list):
        """Push data to the TUI panels."""
        if not self.app:
            return

        rpc_status = self.rpc.get_status()
        rpc_str = f"{'✅' if rpc_status['connected'] else '❌'} {rpc_status['provider']}"

        self.app.call_from_thread(
            self.app.update_all,
            status={
                "last_scan": self._last_scan_time,
                "rpc_status": rpc_str,
                "active_markets": len(markets),
                "balance": balance,
                "dry_run": settings.DRY_RUN,
            },
            markets=markets,
            positions=trades,
        )

    def _log(self, message: str, style: str = ""):
        """Log to both file logger and TUI."""
        log.info(message)
        if self.app:
            try:
                self.app.call_from_thread(self.app.add_log, message, style)
            except Exception:
                pass

    # ── Headless mode (no TUI) ──

    def run_headless(self):
        """Run scanning cycle continuously in headless mode."""
        log.info("=" * 60)
        log.info("Polymarket Weather Bot -- Headless Continuous Mode")
        log.info("=" * 60)

        while True:
            try:
                balance = 0.0
                if settings.FUNDER_ADDRESS:
                    try:
                        balance = self.wallet.get_usdc_balance()
                        positions = self.wallet.get_positions()
                        self.trader.sync_live_positions(positions)
                    except Exception as exc:
                        log.warning(f"Could not fetch wallet data: {exc}")
                else:
                    log.warning("FUNDER_ADDRESS not set -- skipping balance check")

                log.info(f"Balance: ${balance:.2f} USDC")
                log.info(f"Mode: {'DRY RUN' if settings.DRY_RUN else 'LIVE'}")

                markets = self.scanner.scan()
                log.info(f"📊 Found {len(markets)} markets")

                for market in markets:
                    city = market.get("city")
                    if not city:
                        continue

                    forecast = self.weather.fetch_forecast(city)
                    if not forecast:
                        log.warning(f"No forecast for {city}")
                        continue

                    threshold_c = market.get("threshold_c")
                    if threshold_c is None:
                        continue

                    prob = self.edge_model.estimate_with_hourly_data(
                        forecast.get("hourly_temps_c", []),
                        threshold_c,
                        forecast.get("uncertainty_c", 2.0),
                    )

                    forecast_prob_yes = prob["prob_exceeds"]
                    market["edge"] = (market.get("yes_price", 0) or 0) - forecast_prob_yes

                    log.info(
                        f"  {city}: forecast={forecast['forecast_high_c']}°C, "
                        f"threshold={threshold_c}°C, P(exceed)={forecast_prob_yes:.2%}, "
                        f"edge={market['edge']:+.2%}"
                    )

                    signal = self.strategy.evaluate(market, forecast_prob_yes, balance)
                    if signal:
                        result = self.trader.execute_trade(signal)
                        if result:
                            log.info(f"✅ Trade result: {result}")

                log.info("=" * 60)
                log.info(f"Scan complete. Sleeping for {settings.SCAN_INTERVAL} seconds...")
                time.sleep(settings.SCAN_INTERVAL)

            except KeyboardInterrupt:
                log.info("Headless loop stopped by user")
                return
            except Exception as e:
                log.error(f"Error in headless loop: {e}")
                time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="Polymarket Weather Bot")
    parser.add_argument("--headless", action="store_true", help="Run without TUI (single scan)")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run mode")
    parser.add_argument("--live", action="store_true", help="Force live trading mode")
    args = parser.parse_args()

    if args.dry_run:
        settings.DRY_RUN = True
    elif args.live:
        settings.DRY_RUN = False

    bot = WeatherBot()

    if args.headless:
        bot.run_headless()
    else:
        try:
            asyncio.run(bot.run_with_tui())
        except KeyboardInterrupt:
            log.info("Bot stopped by user")
            sys.exit(0)


if __name__ == "__main__":
    main()
