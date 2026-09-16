"""Fix historical dead_market trades — set PnL to 0, exit_price to entry_price."""
import sqlite3, sys
DB = "data/trades.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

before = conn.execute(
    "SELECT SUM(pnl_usd) as total FROM trades WHERE pnl_usd IS NOT NULL"
).fetchone()["total"]

# Fix: dead_market closes at entry → PnL should be $0
# exit_price stored is held-side; should be entry_price (breakeven)
cur = conn.execute("""
    UPDATE trades
    SET pnl_usd = 0.0,
        exit_price = entry_price
    WHERE exit_reason = 'dead_market'
""")
fixed = cur.rowcount
conn.commit()

after = conn.execute(
    "SELECT SUM(pnl_usd) as total FROM trades WHERE pnl_usd IS NOT NULL"
).fetchone()["total"]

print(f"Fixed {fixed} dead_market trades")
print(f"Total PnL before fix: ${before:+.2f}")
print(f"Total PnL after fix:  ${after:+.2f}")
print(f"Removed:              ${before - after:+.2f}")

# Show real PnL breakdown
print("\n=== REAL PnL BY EXIT REASON ===")
rows = conn.execute(
    "SELECT exit_reason, COUNT(*) as n, SUM(pnl_usd) as total "
    "FROM trades WHERE pnl_usd IS NOT NULL GROUP BY exit_reason"
).fetchall()
for r in rows:
    reason = r["exit_reason"] or "open"
    print(f"  {reason:20s} | {r['n']:3d} trades | ${r['total']:+.2f}")
conn.close()
