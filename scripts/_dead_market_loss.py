"""Deep analysis of the 9 losing dead_market trades."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "trades.db"
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

# All dead_market losses
rows = conn.execute(
    "SELECT id, market_question, side, entry_price, exit_price, pnl_usd, "
    "shares, amount_usd, signal_source, edge, materiality "
    "FROM trades WHERE exit_reason='dead_market' AND pnl_usd < 0 "
    "ORDER BY entry_at"
).fetchall()

print("=" * 80)
print("ALL DEAD_MARKET LOSSES (entry/exit are HELD-SIDE prices)")
print("=" * 80)

total_loss = 0
for r in rows:
    ep = r["entry_price"] or 0
    xp = r["exit_price"] or 0
    pnl = r["pnl_usd"] or 0
    shares = r["shares"] or 0
    side = r["side"]
    q = (r["market_question"] or "")[:55]
    edge = r["edge"] or 0
    mat = r["materiality"] or 0
    total_loss += pnl

    # For NO: entry = 1-yes_entry, exit = 1-yes_exit
    # YES price moved UP = bad for NO
    if side == "NO":
        yes_entry = 1.0 - ep
        yes_exit = 1.0 - xp
        yes_move = yes_exit - yes_entry
        print(f"#{r['id']:3d} NO | {q}")
        print(f"     YES: {yes_entry:.3f} -> {yes_exit:.3f} (moved {yes_move:+.3f})")
        print(f"     PnL: ${pnl:+.2f} | Shares: {shares:.1f} | Edge: {edge:.0%} | Mat: {mat:.2f}")
    else:
        print(f"#{r['id']:3d} YES | {q}")
        print(f"     YES: {ep:.3f} -> {xp:.3f} (moved {xp-ep:+.3f})")
        print(f"     PnL: ${pnl:+.2f} | Shares: {shares:.1f} | Edge: {edge:.0%} | Mat: {mat:.2f}")
    print()

print(f"TOTAL DEAD MARKET LOSSES: ${total_loss:.2f}")
print()

# Now check: are these "market resolved opposite to our position" losses?
# Or are they "market delisted/resolved while price was neutral" losses?
print("=" * 80)
print("PATTERN ANALYSIS")
print("=" * 80)

# Group by market
markets = {}
for r in rows:
    q = r["market_question"] or ""
    if q not in markets:
        markets[q] = []
    markets[q].append(r)

for q, trades in sorted(markets.items(), key=lambda x: sum(t["pnl_usd"] or 0 for t in x[1])):
    total = sum(t["pnl_usd"] or 0 for t in trades)
    sides = {t["side"] for t in trades}
    print(f"\n{q[:60]}")
    print(f"  {len(trades)} loss trades | Total: ${total:.2f} | Sides: {sides}")
    for t in trades:
        ep = t["entry_price"] or 0
        xp = t["exit_price"] or 0
        if t["side"] == "NO":
            print(f"    NO entry={ep:.3f} exit={xp:.3f} YES moved {1-xp-(1-ep):+.3f} PnL=${t['pnl_usd']:+.2f}")
        else:
            print(f"    YES entry={ep:.3f} exit={xp:.3f} YES moved {xp-ep:+.3f} PnL=${t['pnl_usd']:+.2f}")

# Check: how many dead_market trades were "market resolved while flat" vs "market resolved against us"?
print("\n" + "=" * 80)
print("DEAD MARKET EXIT TYPE BREAKDOWN")
print("=" * 80)

all_dm = conn.execute(
    "SELECT side, entry_price, exit_price, pnl_usd FROM trades "
    "WHERE exit_reason='dead_market'"
).fetchall()

resolved_against = 0  # PnL significantly negative
resolved_neutral = 0   # PnL near zero
resolved_for = 0      # PnL positive

for r in all_dm:
    pnl = r["pnl_usd"] or 0
    if pnl < -1.0:
        resolved_against += 1
    elif pnl > 1.0:
        resolved_for += 1
    else:
        resolved_neutral += 1

print(f"  Resolved FOR us (PnL > $1): {resolved_for}")
print(f"  Resolved AGAINST us (PnL < -$1): {resolved_against}")
print(f"  Resolved NEUTRAL (|PnL| < $1): {resolved_neutral}")

conn.close()
