import sqlite3

db = r"d:\Github repos\Polymarket bot\data\trades.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row

print("== run-5 trades (id >= 68) ==")
rows = conn.execute("SELECT id, market_question, side, entry_price, exit_price, amount_usd, shares, status, pnl_usd, entry_at, exit_at FROM trades WHERE id >= 68 ORDER BY id").fetchall()
for r in rows:
    q = (r["market_question"] or "")[:45]
    print(f"  #{r['id']:3} {r['status']:12} side={r['side']:3} entry={r['entry_price']:.4f} exit={r['exit_price']} amt=${r['amount_usd']} sh={r['shares']} pnl={r['pnl_usd']} in={r['entry_at']} out={r['exit_at']}  {q}")

print("\n== still-open positions ==")
for r in conn.execute("SELECT id, market_question, side, entry_price, amount_usd, entry_at FROM trades WHERE status='open' ORDER BY id"):
    print(f"  #{r['id']:3} {r['side']:3} entry={r['entry_price']:.4f} amt=${r['amount_usd']} in={r['entry_at']}  {(r['market_question'] or '')[:45]}")
