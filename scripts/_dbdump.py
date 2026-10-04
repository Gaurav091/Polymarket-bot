"""Throwaway: dump all trades with the fields that matter for PnL forensics."""
import sqlite3

c = sqlite3.connect("data/trades.db")
c.row_factory = sqlite3.Row
rows = c.execute(
    "SELECT id, side, entry_price, shares, status, exit_price, pnl_usd, "
    "fees_paid, exit_reason FROM trades ORDER BY id"
).fetchall()

hdr = f"{'id':<4}{'side':<6}{'entry':<8}{'shares':<9}{'status':<13}{'exit':<8}{'pnl':<9}{'fee':<8}reason"
print(hdr)
print("-" * len(hdr))
for r in rows:
    exit_p = r["exit_price"] if r["exit_price"] is not None else -1.0
    pnl = r["pnl_usd"] if r["pnl_usd"] is not None else 0.0
    fee = r["fees_paid"] if r["fees_paid"] is not None else 0.0
    print(
        f"{r['id']:<4}{r['side']:<6}{r['entry_price']:<8.3f}{r['shares']:<9.2f}"
        f"{r['status']:<13}{exit_p:<8.3f}{pnl:<9.2f}{fee:<8.2f}{r['exit_reason'] or ''}"
    )

print()
agg = c.execute(
    "SELECT status, COUNT(*) n, ROUND(SUM(COALESCE(pnl_usd,0)),2) pnl, "
    "ROUND(SUM(COALESCE(fees_paid,0)),2) fees FROM trades GROUP BY status"
).fetchall()
for a in agg:
    print(f"{a['status']:<13} n={a['n']:<4} pnl={a['pnl']:<9} fees={a['fees']}")
