"""
Manual Redemption Script

A standalone tool that scans your wallet for redeemable winning positions
on Polymarket and executes the on-chain redemption to convert them to USDC.
"""

import argparse
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import settings
from utils.logger import log
from bot.rpc_manager import RPCManager
from bot.wallet import Wallet


def main():
    parser = argparse.ArgumentParser(description="Manual Winnings Redemption Script")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run mode (no transactions)")
    args = parser.parse_args()

    if args.dry_run:
        settings.DRY_RUN = True
        log.info("⚠️ RUNNING IN DRY-RUN MODE (No real transactions)")

    log.info("=" * 60)
    log.info("Starting Manual Redemption Scan")
    log.info("=" * 60)

    try:
        rpc = RPCManager()
        wallet = Wallet(rpc)
        
        log.info(f"Fetching positions for wallet: {wallet.address}...")
        positions = wallet.get_positions()
        
        if not positions:
            log.info("No positions found. Exiting.")
            return

        redeemable_positions = [p for p in positions if p.get("redeemable") is True]
        
        if not redeemable_positions:
            log.info("❌ No redeemable winning positions found at this time.")
            return

        log.info(f"Found {len(redeemable_positions)} redeemable positions! Processing...")

        standard_positions = []
        negrisk_cids = []
        
        for pos in redeemable_positions:
            if pos.get("negativeRisk"):
                cid = pos.get("conditionId")
                if cid:
                    negrisk_cids.append(cid)
            else:
                standard_positions.append(pos)

        # 1. Process Negative Risk (Batch)
        if negrisk_cids:
            log.info(f"--- Redeeming {len(negrisk_cids)} Negative Risk positions ---")
            if wallet.redeem_negrisk(negrisk_cids):
                log.info("✅ Batch NegRisk redemption successful")
            else:
                log.warning("❌ Batch NegRisk redemption failed")

        # 2. Process Standard (Sequential)
        for pos in standard_positions:
            condition_id = pos.get("conditionId")
            if not condition_id:
                continue
                
            title = pos.get("title", "Unknown Market")
            outcome_str = pos.get("outcome", "No")
            outcome_index = 0 if outcome_str.lower() == "yes" else 1
            
            log.info(f"--- Redeeming Standard: {title} ({outcome_str}) ---")
            if wallet.redeem_positions(condition_id, outcome_index):
                log.info(f"✅ Successfully redeemed {title}")
            else:
                log.warning(f"❌ Failed to redeem {title}")

        log.info("=" * 60)
        log.info("Redemption Process Complete.")
        log.info(f"Final USDC balance: ${wallet.get_usdc_balance():.2f}")
        log.info("=" * 60)

    except KeyboardInterrupt:
        log.info("Script stopped by user.")
    except Exception as e:
        log.error(f"Error executing manual redemption script: {e}", exc_info=True)


if __name__ == "__main__":
    main()
