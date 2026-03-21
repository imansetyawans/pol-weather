import json
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from bot.rpc_manager import RPCManager
from bot.wallet import Wallet

w = Wallet(RPCManager())
pos = w.get_positions()

for p in pos:
    print(f"Question: {p.get('title')}")
    print(f"ConditionID: {p.get('conditionId')}")
    print(f"End Date (Trading Stops): {p.get('endDate')}")
    print(f"Redeemable: {p.get('redeemable')}")
    print(f"Current Price (Live API): {p.get('curPrice')}")
    print("-" * 40)
