"""Calculate what PnL would be with the dead_market fix applied."""
import sqlite3, sys
DB = "data/trades.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Show dead_market trades and what their PnL should be (breakeven)
rows = conn.execute(
    "SELECT id, side, entry_price, exit_price, pnl_usd, shares, exit_reason "
    "FROM trades WHERE exit_reason='dead_market' ORDER BY id"
).fetchall()

total_db = sum(r["pnl_usd"] for r in rows)
total_fixed = 0.0
print("=== DEAD MARKET EXITS — ACTUAL vs FIXED ===")
print(f"{'#':>4} {'Side':>4} {'Entry':>7} {'DB Exit':>8} {'DB PnL':>9} {'Fixed PnL':>10}")
for r in rows:
    ep = r["entry_price"]
    side = r["side"]
    # With fix: exit_yes = ep if YES else 1-ep → exit_held = ep → PnL = 0
    fixed_pnl = 0.0
    total_fixed += fixed_pnl
    print(f"#{r['id']:3d} {side:>4} {ep:7.3f} {r['exit_price']:8.3f} "
          f"${r['pnl_usd']:+9.2f} ${fixed_pnl:+10.2f}")

print(f"\nTotal dead_market DB PnL:  ${total_db:+.2f}")
print(f"Total dead_market Fixed:   ${total_fixed:+.2f}")
print(f"Phantom PnL removed:       ${total_db - total_fixed:+.2f}")

# Overall PnL
all_rows = conn.execute("SELECT SUM(pnl_usd) as total FROM trades WHERE pnl_usd IS NOT NULL").fetchone()
real_total = all_rows["total"] - total_db + total_fixed
print(f"\n=== OVERALL PnL ===")
print(f"Current DB total: ${all_rows['total']:+.2f}")
print(f"After fix:        ${real_total:+.2f}")
print(f"Difference:       ${all_rows['total'] - real_total:+.2f}")

# Breakdown by exit_reason
print(f"\n=== PnL BY EXIT REASON ===")
reasons = conn.execute(
    "SELECT exit_reason, COUNT(*) as n, SUM(pnl_usd) as total "
    "FROM trades WHERE pnl_usd IS NOT NULL GROUP BY exit_reason"
).fetchall()
for r in reasons:
    reason = r["exit_reason"] or "NULL (still open)"
    print(f"  {reason:20s} | {r['n']:3d} trades | ${r['total']:+.2f}")

conn.close()
