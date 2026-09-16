"""Backfill fees_paid for all historical closed trades and recompute PnL."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from bot.journal import init_db, _conn

init_db()  # runs migration — adds fees_paid column if missing
conn = _conn()
FEE_RATE = 0.04  # Default Politics/Tech rate
rows = conn.execute(
    "SELECT id, side, entry_price, exit_price, shares, pnl_usd "
    "FROM trades WHERE status != 'open' AND fees_paid IS NULL"
).fetchall()

print(f"Backfilling fees for {len(rows)} closed trades (feeRate={FEE_RATE})")
total_fee = 0.0
total_pnl_before = 0.0
total_pnl_after = 0.0

for (tid, side, entry, exit_price, shares, old_pnl) in rows:
    if exit_price is None or shares is None:
        continue
    # entry_price is held-side; exit_price is held-side (after fix)
    entry_fee = shares * FEE_RATE * entry * (1 - entry)
    exit_fee = shares * FEE_RATE * exit_price * (1 - exit_price)
    fee = entry_fee + exit_fee
    gross_pnl = (exit_price - entry) * shares
    new_pnl = gross_pnl - fee
    conn.execute(
        "UPDATE trades SET fees_paid = ?, pnl_usd = ? WHERE id = ?",
        (fee, new_pnl, tid),
    )
    total_fee += fee
    total_pnl_before += old_pnl or 0
    total_pnl_after += new_pnl

conn.commit()

# Show summary
print(f"\nTotal fees applied:     ${total_fee:.2f}")
print(f"PnL before fees:        ${total_pnl_before:+.2f}")
print(f"PnL after fees:         ${total_pnl_after:+.2f}")

# Breakdown by exit_reason
print("\n=== PnL BY EXIT REASON (after fees) ===")
rows2 = conn.execute(
    "SELECT exit_reason, COUNT(*) as n, SUM(pnl_usd) as pnl, SUM(fees_paid) as fees "
    "FROM trades WHERE status != 'open' GROUP BY exit_reason"
).fetchall()
for r in rows2:
    reason = r[0] or "unknown"
    print(f"  {reason:20s} | {r[1]:3d} trades | PnL=${r[2]:+.2f} | Fees=${r[3]:.2f}")

# Grand total
grand = conn.execute(
    "SELECT SUM(pnl_usd) as pnl, SUM(fees_paid) as fees FROM trades WHERE status != 'open'"
).fetchone()
pnl_total = grand[0] or 0
fees_total = grand[1] or 0
print(f"\nGRAND TOTAL: PnL=${pnl_total:+.2f} | Fees=${fees_total:.2f}")
conn.close()
