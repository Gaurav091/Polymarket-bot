import sys, time
sys.path.insert(0, r"d:\Github repos\Polymarket bot")
from bot.markets import fetch_active_markets, filter_niche
from bot.quant import compute_quant_signal, fetch_price_history, fetch_order_book

markets = filter_niche(fetch_active_markets(200))
print(f"niche markets: {len(markets)}")
t0 = time.time()
for m in markets[:8]:
    tid = m.token_id("YES")
    hist = fetch_price_history(tid)
    book = fetch_order_book(tid)
    qs = compute_quant_signal(m)
    print(f"  {qs.direction:8} str={qs.strength:.2f} (mom={qs.momentum:+.2f} mrev={qs.mean_rev:+.2f} flow={qs.flow:+.2f}) srcs={qs.sources_used} hist={len(hist)} book={'Y' if book else 'N'} — {m.question[:50]}")
print(f"elapsed: {time.time()-t0:.1f}s")
