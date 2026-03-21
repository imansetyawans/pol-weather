"""
Manual Take-Profit Script

A standalone tool that scans your open Polymarket weather positions
and compares them to the live market prices. If a position's NO price
exceeds the configured threshold, it immediately executes a SELL FAK order.
"""

import argparse
import sys
import os

# Add the project root to the Python path so local imports work correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import settings
from utils.logger import log
from bot.rpc_manager import RPCManager
from bot.wallet import Wallet
from bot.market_scanner import MarketScanner
from bot.strategy import Strategy
from bot.trader import Trader


def main():
    parser = argparse.ArgumentParser(description="Manual Take Profit Execution Script")
    parser.add_argument(
        "--threshold",
        type=float,
        default=settings.TAKE_PROFIT_THRESHOLD,
        help="Price threshold to take profit (e.g. 0.99 for 99¢)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run mode (no live trades)")
    args = parser.parse_args()

    if args.dry_run:
        settings.DRY_RUN = True
        log.info("⚠️ RUNNING IN DRY-RUN MODE (No real execution)")

    # Override the settings threshold if provided via CLI
    settings.TAKE_PROFIT_THRESHOLD = args.threshold

    log.info("=" * 60)
    log.info(f"Starting Manual Take-Profit Scan | Threshold: {settings.TAKE_PROFIT_THRESHOLD:.4f}")
    log.info("=" * 60)

    try:
        rpc = RPCManager()
        wallet = Wallet(rpc)
        scanner = MarketScanner()
        
        # We explicitly inject the updated threshold into the Strategy
        strategy = Strategy()
        strategy.take_profit_threshold = settings.TAKE_PROFIT_THRESHOLD
        
        trader = Trader()

        log.info("Fetching live wallet positions from Gamma API...")
        positions = wallet.get_positions()
        
        if not positions:
            log.info("No open positions found in wallet. Exiting.")
            return

        active_no_positions = len([p for p in positions if p.get("outcome") == "No"])
        log.info(f"Found {len(positions)} total positions ({active_no_positions} active 'NO' positions).")
        
        # Sync trader to prevent duplicate trade log warnings 
        trader.sync_live_positions(positions)

        log.info("Scanning Polymarket for live weather prices...")
        markets = scanner.scan()
        log.info(f"Found {len(markets)} active weather markets.")

        sold_any = False
        for market in markets:
            city = market.get("city")
            if not city:
                continue

            # Find matching position in our wallet
            position = next(
                (p for p in positions if p.get("conditionId", "").lower() == market.get("condition_id", "").lower()),
                None
            )
            
            if position:
                # Use strategy module to cleanly evaluate the TP condition
                tp_signal = strategy.evaluate_take_profit(market, position)
                
                if tp_signal:
                    log.info(f"🎯 Take profit triggered for {city}! Executing manual sell...")
                    result = trader.execute_trade(tp_signal)
                    
                    if result:
                        log.info(
                            f"✅ Trade executed: SELL NO on {city} | "
                            f"{tp_signal.get('position_size_shares', 0):.4f} shares"
                        )
                        sold_any = True
                    else:
                        log.warning(f"⚠ Take profit failed for {city}")

        if not sold_any:
            log.info("❌ No active positions met the take-profit threshold right now.")
            
        log.info("=" * 60)
        log.info("Manual Take-Profit Scan Complete.")
        
    except KeyboardInterrupt:
        log.info("Script stopped by user.")
    except Exception as e:
        log.error(f"Error executing manual take-profit script: {e}", exc_info=True)


if __name__ == "__main__":
    main()
