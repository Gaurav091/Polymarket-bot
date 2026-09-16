"""Deep-dive: what makes winners win and losers lose."""
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

conn = sqlite3.connect("data/trades.db")
conn.row_factory = sqlite3.Row

# 1. STOP LOSS trades — what do they have in common?
print("=" * 70)
print("STOP LOSS TRADES ANALYSIS (53 trades, -$233.26)")
print("=" * 70)

# Entry price distribution of SL trades
sl = conn.execute("""
    SELECT entry_price, side, market_question, holding_minutes, shares,
           pnl_usd, fees_paid, exit_price
    FROM trades WHERE exit_reason = 'stop_loss' ORDER BY entry_price
""").fetchall()

# Group by side
sl_yes = [r for r in sl if r["side"] == "YES"]
sl_no = [r for r in sl if r["side"] == "NO"]
print(f"\nYES stops: {len(sl_yes)} trades, total PnL=${sum(r['pnl_usd'] for r in sl_yes):+.2f}")
print(f"NO stops:  {len(sl_no)} trades, total PnL=${sum(r['pnl_usd'] for r in sl_no):+.2f}")

# Entry price buckets
for label, lo, hi in [("0.00-0.20", 0, 0.20), ("0.20-0.40", 0.20, 0.40),
                       ("0.40-0.60", 0.40, 0.60), ("0.60-0.80", 0.60, 0.80)]:
    subset = [r for r in sl if lo <= r["entry_price"] < hi]
    if subset:
        print(f"  {label}: {len(subset)} trades, avg PnL=${sum(r['pnl_usd'] for r in subset)/len(subset):+.2f}")

# Holding time of SL trades
short_sl = [r for r in sl if r["holding_minutes"] and r["holding_minutes"] < 5]
long_sl = [r for r in sl if r["holding_minutes"] and r["holding_minutes"] >= 5]
print(f"\nSL within 5 min: {len(short_sl)} trades, avg PnL=${sum(r['pnl_usd'] for r in short_sl)/max(1,len(short_sl)):+.2f}")
print(f"SL after 5 min: {len(long_sl)} trades, avg PnL=${sum(r['pnl_usd'] for r in long_sl)/max(1,len(long_sl)):+.2f}")

# 2. TIMEOUT trades — detailed analysis
print(f"\n{'='*70}")
print("TIMEOUT TRADES ANALYSIS (161 trades, -$124.39)")
print(f"{'='*70}")

# What was the unrealized PnL at timeout?
# If timeout happens at 12 min, what was the price doing?
timeout = conn.execute("""
    SELECT entry_price, side, exit_price, pnl_usd, fees_paid, shares, holding_minutes
    FROM trades WHERE exit_reason = 'timeout'
""").fetchall()

# Entry price vs PnL for timeouts
for label, lo, hi in [("0.00-0.20", 0, 0.20), ("0.20-0.40", 0.20, 0.40),
                       ("0.40-0.60", 0.40, 0.60), ("0.60-0.80", 0.60, 0.80)]:
    subset = [r for r in timeout if lo <= r["entry_price"] < hi]
    if subset:
        wins = len([r for r in subset if r["pnl_usd"] > 0])
        print(f"  {label}: {len(subset)} trades, {wins} wins ({wins/len(subset)*100:.0f}%), "
              f"avg PnL=${sum(r['pnl_usd'] for r in subset)/len(subset):+.2f}")

# Were timeouts actually profitable at the time of exit?
print("\nTimeout exit_price vs entry_price:")
moving_up = len([r for r in timeout if r["exit_price"] and r["entry_price"] and
                 ((r["side"] == "YES" and r["exit_price"] > r["entry_price"]) or
                  (r["side"] == "NO" and (1-r["exit_price"]) > r["entry_price"]))])
moving_down = len([r for r in timeout if r["exit_price"] and r["entry_price"] and
                   ((r["side"] == "YES" and r["exit_price"] <= r["entry_price"]) or
                    (r["side"] == "NO" and (1-r["exit_price"]) <= r["entry_price"]))])
print(f"  Favorable direction: {moving_up}/{len(timeout)} ({moving_up/len(timeout)*100:.0f}%)")
print(f"  Unfavorable direction: {moving_down}/{len(timeout)} ({moving_down/len(timeout)*100:.0f}%)")

# 3. TAKE PROFIT trades — what makes them work?
print(f"\n{'='*70}")
print("TAKE PROFIT TRADES ANALYSIS (48 trades, +$186.36)")
print(f"{'='*70}")

tp = conn.execute("""
    SELECT entry_price, side, exit_price, pnl_usd, fees_paid, shares, holding_minutes, market_question
    FROM trades WHERE exit_reason = 'take_profit'
""").fetchall()

for label, lo, hi in [("0.00-0.20", 0, 0.20), ("0.20-0.40", 0.20, 0.40),
                       ("0.40-0.60", 0.40, 0.60), ("0.60-0.80", 0.60, 0.80),
                       ("0.80-1.00", 0.80, 1.01)]:
    subset = [r for r in tp if lo <= r["entry_price"] < hi]
    if subset:
        print(f"  {label}: {len(subset)} trades, avg PnL=${sum(r['pnl_usd'] for r in subset)/len(subset):+.2f}")

tp_yes = len([r for r in tp if r["side"] == "YES"])
tp_no = len([r for r in tp if r["side"] == "NO"])
print(f"\nYES take profits: {tp_yes}, NO take profits: {tp_no}")

# 4. DEAD MARKET trades — pure fee loss
print(f"\n{'='*70}")
print("DEAD MARKET TRADES (47 trades, -$75.98)")
print(f"{'='*70}")
dead = conn.execute("""
    SELECT entry_price, side, pnl_usd, fees_paid
    FROM trades WHERE exit_reason = 'dead_market'
""").fetchall()
dead_yes = len([r for r in dead if r["side"] == "YES"])
dead_no = len([r for r in dead if r["side"] == "NO"])
print(f"YES dead: {dead_yes}, NO dead: {dead_no}")
print("These are 100% fee loss — market went unreachable before exit")

# 5. Break-even by entry price (gross PnL = net + fees)
print(f"\n{'='*70}")
print("GROSS PnL BY ENTRY PRICE (before fees)")
print(f"{'='*70}")
for label, lo, hi in [("0.00-0.20", 0, 0.20), ("0.20-0.40", 0.20, 0.40),
                       ("0.40-0.50", 0.40, 0.50), ("0.50-0.60", 0.50, 0.60),
                       ("0.60-0.70", 0.60, 0.70), ("0.70-0.80", 0.70, 0.80),
                       ("0.80-1.00", 0.80, 1.01)]:
    row = conn.execute("""
        SELECT COUNT(*) as n, SUM(pnl_usd + fees_paid) as gross, SUM(fees_paid) as fees,
               SUM(pnl_usd) as net
        FROM trades WHERE entry_price >= ? AND entry_price < ? AND status != 'open'
    """, (lo, hi)).fetchone()
    if row["n"] > 0:
        print(f"  {label:10s} | {row['n']:3d} | Gross=${row['gross'] or 0:+8.2f} | Fees=${row['fees'] or 0:6.2f} | Net=${row['net'] or 0:+8.2f}")

# 6. The critical question: what's the break-even win rate?
print(f"\n{'='*70}")
print("BREAK-EVEN ANALYSIS")
print(f"{'='*70}")

# For trades above 0.30 entry (the profitable zone)
good_zone = conn.execute("""
    SELECT COUNT(*) as n, 
           SUM(pnl_usd + fees_paid) as gross,
           SUM(fees_paid) as fees,
           AVG(pnl_usd) as avg_net,
           AVG(pnl_usd + fees_paid) as avg_gross
    FROM trades WHERE entry_price >= 0.30 AND status != 'open'
""").fetchone()

print("\nEntry >= $0.30 (current MIN_ENTRY_PRICE):")
print(f"  Trades: {good_zone['n']}")
print(f"  Gross PnL: ${good_zone['gross'] or 0:+.2f}")
print(f"  Total fees: ${good_zone['fees'] or 0:.2f}")
net_30 = (good_zone['gross'] or 0) - (good_zone['fees'] or 0)
print(f"  Net PnL: ${net_30:+.2f}")

# Trades above 0.40 entry
best_zone = conn.execute("""
    SELECT COUNT(*) as n,
           SUM(pnl_usd + fees_paid) as gross,
           SUM(fees_paid) as fees,
           SUM(pnl_usd) as net
    FROM trades WHERE entry_price >= 0.40 AND status != 'open'
""").fetchone()
if best_zone["n"] > 0:
    print("\nEntry >= $0.40:")
    print(f"  Trades: {best_zone['n']}")
    print(f"  Gross PnL: ${best_zone['gross'] or 0:+.2f}")
    print(f"  Total fees: ${best_zone['fees'] or 0:.2f}")
    print(f"  Net PnL: ${best_zone['net'] or 0:+.2f}")

# 7. What if we removed ALL dead_market and only had TP + resolved?
print(f"\n{'='*70}")
print("SCENARIO: What if we only took trades that would TP?")
print(f"{'='*70}")
tp_stats = conn.execute("""
    SELECT COUNT(*) as n, SUM(pnl_usd) as total, SUM(fees_paid) as fees
    FROM trades WHERE exit_reason IN ('take_profit', 'resolved')
""").fetchone()
sl_stats = conn.execute("""
    SELECT COUNT(*) as n, SUM(pnl_usd) as total, SUM(fees_paid) as fees
    FROM trades WHERE exit_reason = 'stop_loss'
""").fetchone()
print(f"  Take profits: {tp_stats['n']} trades, PnL=${tp_stats['total'] or 0:+.2f}, Fees=${tp_stats['fees'] or 0:.2f}")
print(f"  Stop losses:  {sl_stats['n']} trades, PnL=${sl_stats['total'] or 0:+.2f}, Fees=${sl_stats['fees'] or 0:.2f}")

# The SL:TP ratio and fee ratio
if sl_stats["n"] > 0 and tp_stats["n"] > 0:
    ratio = sl_stats["n"] / tp_stats["n"]
    avg_sl_pnl = sl_stats["total"] / sl_stats["n"]
    avg_tp_pnl = tp_stats["total"] / tp_stats["n"]
    print(f"\n  SL:TP ratio = {ratio:.1f}:1")
    print(f"  Avg SL loss = ${avg_sl_pnl:.2f}")
    print(f"  Avg TP win = ${avg_tp_pnl:.2f}")
    print(f"  Need SL:TP ratio < {abs(avg_tp_pnl/avg_sl_pnl):.1f}:1 to be profitable (ignoring fees)")
    
    # Including fees
    avg_sl_net = (sl_stats["total"] + sl_stats["fees"]) / sl_stats["n"]
    avg_tp_net = (tp_stats["total"] + tp_stats["fees"]) / tp_stats["n"]
    if avg_sl_net != 0:
        print(f"  Need SL:TP ratio < {abs(avg_tp_net/avg_sl_net):.1f}:1 to be profitable (after fees)")

conn.close()
