import sys
sys.path.insert(0, r"d:\Github repos\Polymarket bot")
import requests, json

CLOB = "https://clob.polymarket.com"

# grab a few niche markets the same way the bot does
from bot.markets import fetch_active_markets
markets = fetch_active_markets()[:5]

for m in markets:
    tid = m.token_id("YES")
    if not tid:
        continue
    r = requests.get(f"{CLOB}/book", params={"token_id": tid}, timeout=30, verify=False)
    book = r.json()
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    print(f"\n== {m.question[:60]}")
    print(f"   yes_price={m.yes_price}  bids={len(bids)}  asks={len(asks)}")
    if bids:
        bb = bids[0]; ba = bids[-1]
        print(f"   best bid: {bb}   worst bid: {ba}")
    if asks:
        ba = asks[0]; bz = asks[-1]
        print(f"   best ask: {ba}   worst ask: {bz}")
    bd = sum(float(b['price'])*float(b['size']) for b in bids)
    ad = sum(float(a['price'])*float(a['size']) for a in asks)
    tot = bd + ad
    flow = (bd - ad)/tot*2.0 if tot else 0.0
    print(f"   bid_depth=${bd:.2f}  ask_depth=${ad:.2f}  flow={flow:.3f}")
