import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from bot.rpc_manager import RPCManager
from bot.wallet import Wallet
from bot.market_scanner import MarketScanner

w = Wallet(RPCManager())
pos = w.get_positions()
s = MarketScanner()
m = s.scan(limit_top=False)

for p in pos:
    in_active = any(x.get("condition_id", "").lower() == p.get("conditionId", "").lower() for x in m)
    print(f"[POS] {p.get('title')}")
    print(f"      Outcome: {p.get('outcome')} (Is NO: {p.get('outcome') == 'No'})")
    print(f"      Size: {p.get('size')} | avgPrice: {p.get('avgPrice')}")
    print(f"      Active Market Found (Take-Profit candidate): {in_active}")
    if in_active:
        market = next((x for x in m if x.get("condition_id", "").lower() == p.get("conditionId", "").lower()), None)
        print(f"      Live NO Price: {market.get('no_price')}")
    print("-" * 40)
