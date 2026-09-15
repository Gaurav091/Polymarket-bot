"""Probe free CLOB endpoints (book + trades) on a real token."""
import sys
import time

sys.path.insert(0, r"d:\Github repos\Polymarket bot")
import requests  # noqa: E402

from bot.markets import fetch_active_markets  # noqa: E402

ms = []
for attempt in range(4):
    ms = fetch_active_markets(200)
    if ms:
        break
    print(f"gamma retry {attempt}...")
    time.sleep(3)

ms = [x for x in ms if x.tokens and x.tokens[0].get("token_id")]
print("markets with tokens:", len(ms))
m = ms[0]
tid = m.tokens[0]["token_id"]
print("market:", m.question[:50])
print("token:", tid[:30], "...")

r = requests.get("https://clob.polymarket.com/book",
                 params={"token_id": tid}, timeout=30, verify=False)
print("book status:", r.status_code)
d = r.json()
bids, asks = d.get("bids", []), d.get("asks", [])
print("bids:", len(bids), "asks:", len(asks))
if bids:
    print("best bid:", bids[0])
if asks:
    print("best ask:", asks[-1])

r2 = requests.get("https://clob.polymarket.com/trades",
                  params={"market": tid, "limit": 5}, timeout=30, verify=False)
print("trades status:", r2.status_code)
try:
    t = r2.json()
    print("recent trades:", len(t) if isinstance(t, list) else t)
    if isinstance(t, list) and t:
        print("sample:", {k: t[0].get(k) for k in ("price", "side", "size")})
except Exception as e:
    print("trades parse error:", e)
