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

# Minimal Gnosis CTF ABI for redeemPositions
CTF_ABI = json.loads('[{"constant":false,"inputs":[{"name":"collateralToken","type":"address"},'
                       '{"name":"parentCollectionId","type":"bytes32"},{"name":"conditionId","type":"bytes32"},'
                       '{"name":"indexSets","type":"uint256[]"}],"name":"redeemPositions","outputs":[],'
                       '"payable":false,"stateMutability":"nonpayable","type":"function"}]')

# Minimal NegRiskAdapter ABI
NEGRISK_ABI = json.loads('[{"constant":false,"inputs":[{"name":"conditionId","type":"bytes32"},'
                          '{"name":"indexSets","type":"uint256[]"}],"name":"redeemPositions","outputs":[],'
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
            return 0.0 # Return 0.0 instead of raising to avoid crashing the loop

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

    def redeem_positions(self, condition_id: str, outcome_index: int) -> bool:
        """
        Execute an on-chain redemption for a given condition.
        
        Args:
            condition_id: The 32-byte condition ID hex string
            outcome_index: 0 for Yes, 1 for No
            
        Returns:
            True if successful transaction, False otherwise
        """
        try:
            log.info(f"[wallet] 🏦 Initiating on-chain redemption for {condition_id}...")
            
            if settings.DRY_RUN:
                log.info(f"[wallet] (DRY-RUN) Would redeem condition {condition_id} with outcome index {outcome_index}")
                return True

            w3 = self.rpc.w3
            # Index sets: binary markets use 1 for Yes (0) and 2 for No (1)
            index_set = [1 << outcome_index]
            
            ctf = w3.eth.contract(
                address=w3.to_checksum_address(settings.CTF_ADDRESS),
                abi=CTF_ABI
            )
            
            # Prepare transaction
            from_addr = w3.to_checksum_address(self.address)
            
            # parentCollectionId is always zero for base markets
            parent_id = "0x" + "0" * 64
            
            tx = ctf.functions.redeemPositions(
                w3.to_checksum_address(settings.USDC_ADDRESS),
                parent_id,
                condition_id,
                index_set
            ).build_transaction({
                'from': from_addr,
                'nonce': w3.eth.get_transaction_count(from_addr),
                'gasPrice': w3.eth.gas_price,
            })
            
            # Sign and send
            signed_tx = w3.eth.account.sign_transaction(tx, private_key=settings.PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            log.info(f"[wallet] 🚀 Redemption TX Sent: {tx_hash.hex()}")
            
            # Wait for receipt
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.status == 1:
                log.info(f"[wallet] ✅ Redemption successful for {condition_id}")
                return True
            else:
                log.error(f"[wallet] ❌ Redemption transaction failed for {condition_id}")
                return False
                
        except Exception as e:
            log.error(f"[wallet] Error during standard redemption: {e}")
            return False

    def redeem_negrisk(self, condition_id: str, outcome_index: int = 1) -> bool:
        """
        Execute redemption for a Negative Risk market via the specialized Adapter.
        
        Args:
            condition_id: 32-byte condition ID hex string
            outcome_index: 0 for Yes, 1 for No
            
        Returns:
            True if successful transaction, False otherwise
        """
        try:
            log.info(f"[wallet] 🏦 Initiating NegRisk redemption for {condition_id}...")
            
            if settings.DRY_RUN:
                log.info(f"[wallet] (DRY-RUN) Would redeem NegRisk condition: {condition_id}")
                return True

            w3 = self.rpc.w3
            # Clean condition_id
            if condition_id.startswith("0x"):
                cid_hex = condition_id[2:]
            else:
                cid_hex = condition_id
            
            if len(cid_hex) != 64:
                raise ValueError(f"Invalid condition_id length: {len(cid_hex)}")
                
            cid_bytes = bytes.fromhex(cid_hex)

            adapter = w3.eth.contract(
                address=w3.to_checksum_address(settings.NEG_RISK_ADAPTER),
                abi=NEGRISK_ABI
            )
            
            from_addr = w3.to_checksum_address(self.address)
            
            # Index set: binary No is 2 (1 << 1), Yes is 1 (1 << 0)
            index_sets = [1 << outcome_index]
            
            log.info(f"[wallet] Using NegRiskAdapter.redeemPositions({condition_id}, {index_sets})")

            tx = adapter.functions.redeemPositions(
                cid_bytes,
                index_sets
            ).build_transaction({
                'from': from_addr,
                'nonce': w3.eth.get_transaction_count(from_addr),
                'gas': 250000,
                'gasPrice': int(w3.eth.gas_price * 1.5), # Aggressive gas for redemption
            })
            
            signed_tx = w3.eth.account.sign_transaction(tx, private_key=settings.PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            log.info(f"[wallet] 🚀 NegRisk Redemption TX Sent: {tx_hash.hex()}")
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status == 1:
                log.info(f"[wallet] ✅ NegRisk redemption successful for {condition_id}")
                return True
            else:
                log.error(f"[wallet] ❌ NegRisk redemption transaction failed (reverted) for {condition_id}")
                return False
                
        except Exception as e:
            log.error(f"[wallet] Error during NegRisk redemption: {e}")
            return False
