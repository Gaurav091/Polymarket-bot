"""Analyze specific losing markets from the past 20 trades."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "trades.db"
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

# Check the specific losing markets
markets = ["Lake Mead", "London", "National Party", "Dodgers"]
for m in markets:
    rows = conn.execute(
        "SELECT entry_price, exit_price, pnl_usd, amount_usd, exit_reason, "
        "signal_source, edge, holding_minutes, market_question "
        "FROM trades WHERE market_question LIKE ? ORDER BY entry_at",
        (f"%{m}%",),
    ).fetchall()
    print(f"=== {m} ({len(rows)} trades) ===")
    total_pnl = sum(r["pnl_usd"] or 0 for r in rows)
    for r in rows:
        ep = r["entry_price"] or 0
        xp = r["exit_price"] or 0
        pnl = r["pnl_usd"] or 0
        amt = r["amount_usd"] or 0
        er = r["exit_reason"] or "?"
        edge = r["edge"] or 0
        hm = r["holding_minutes"] or 0
        q = (r["market_question"] or "")[:50]
        tag = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BE"
        print(f"  {tag:4} | {ep:.3f} -> {xp:.3f} | PnL: ${pnl:+.2f} | Bet: ${amt:.2f} | Edge: {edge:.0%} | Hold: {hm:.0f}m | {er}")
    print(f"  TOTAL: ${total_pnl:+.2f}")
    print()

# Check SL exit prices vs entry prices
print("=== STOP LOSS EXIT ANALYSIS ===")
sl_rows = conn.execute(
    "SELECT entry_price, exit_price, amount_usd FROM trades WHERE exit_reason='stop_loss'"
).fetchall()
drops = []
for r in sl_rows:
    ep = r["entry_price"] or 0
    xp = r["exit_price"] or 0
    if ep > 0:
        drop_pct = (ep - xp) / ep * 100
        drops.append(drop_pct)

if drops:
    print(f"  SL drops: min={min(drops):.1f}% avg={sum(drops)/len(drops):.1f}% max={max(drops):.1f}%")
    print(f"  SL count: {len(drops)}")

# Check TAKE_PROFIT exit prices vs entry prices
print("\n=== TAKE PROFIT EXIT ANALYSIS ===")
tp_rows = conn.execute(
    "SELECT entry_price, exit_price, amount_usd, pnl_usd FROM trades WHERE exit_reason='take_profit'"
).fetchall()
if tp_rows:
    gains = []
    for r in tp_rows:
        ep = r["entry_price"] or 0
        xp = r["exit_price"] or 0
        if ep > 0:
            gain_pct = (xp - ep) / ep * 100
            gains.append(gain_pct)
    print(f"  TP gains: min={min(gains):.1f}% avg={sum(gains)/len(gains):.1f}% max={max(gains):.1f}%")
    print(f"  TP count: {len(gains)}")

# What about timeout - these often lose at <0.20
print("\n=== TIMEOUT AT <0.20 ENTRY ===")
timeout_low = conn.execute(
    "SELECT entry_price, exit_price, pnl_usd FROM trades WHERE exit_reason='timeout' AND entry_price < 0.20"
).fetchall()
if timeout_low:
    total = sum(r["pnl_usd"] or 0 for r in timeout_low)
    print(f"  Count: {len(timeout_low)} | Total PnL: ${total:.2f}")

# Dead market analysis — which direction do we win?
print("\n=== DEAD MARKET EXIT DIRECTION ===")
dm = conn.execute(
    "SELECT side, pnl_usd, entry_price, exit_price FROM trades WHERE exit_reason='dead_market'"
).fetchall()
dm_wins = [r for r in dm if (r["pnl_usd"] or 0) > 0]
dm_losses = [r for r in dm if (r["pnl_usd"] or 0) < 0]
dm_be = [r for r in dm if (r["pnl_usd"] or 0) == 0]
print(f"  Total dead_market: {len(dm)} | Wins: {len(dm_wins)} | Losses: {len(dm_losses)} | BE: {len(dm_be)}")
if dm_wins:
    avg_win = sum(r["pnl_usd"] or 0 for r in dm_wins) / len(dm_wins)
    print(f"  Avg win: ${avg_win:.2f}")
if dm_losses:
    avg_loss = sum(r["pnl_usd"] or 0 for r in dm_losses) / len(dm_losses)
    print(f"  Avg loss: ${avg_loss:.2f}")

# Check: are the losses from "dead market" actually just position closing at current price?
print("\n=== DEAD MARKET LOSSES (potential data issue?) ===")
for r in dm_losses:
    ep = r["entry_price"] or 0
    xp = r["exit_price"] or 0
    side = r["side"]
    pnl = r["pnl_usd"] or 0
    if side == "NO":
        # NO trade: entered at (1-yes_price), exit at (1-exit_yes)
        # Loss means price moved UP (bad for NO)
        print(f"  NO @ {ep:.3f} -> {xp:.3f} | PnL: ${pnl:+.2f} | YES moved {'up' if xp > ep else 'down'}")
    else:
        print(f"  YES @ {ep:.3f} -> {xp:.3f} | PnL: ${pnl:+.2f}")

conn.close()
