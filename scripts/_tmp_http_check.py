import sys
sys.path.insert(0, r"d:\Github repos\Polymarket bot")
from bot.markets import fetch_active_markets, filter_niche
from bot.quant import fetch_price_history, fetch_order_book

markets = filter_niche(fetch_active_markets(200))
m = markets[0]
tid = m.token_id("YES")
print(f"market: {m.question[:60]}")
print(f"token_id: {tid}")

hist = fetch_price_history(tid)
print(f"fetch_price_history: {len(hist)} points, first={hist[0] if hist else None}")

book = fetch_order_book(tid)
print(f"fetch_order_book: {'OK' if book else 'None'}")
if book:
    print(f"  bids={len(book.get('bids', []))} asks={len(book.get('asks', []))}")
