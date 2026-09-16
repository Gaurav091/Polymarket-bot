"""Project profitability under new parameters using historical trade data."""
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

conn = sqlite3.connect("data/trades.db")
conn.row_factory = sqlite3.Row

print("=" * 70)
print("PROFITABILITY PROJECTION — NEW PARAMETERS")
print("=" * 70)

# New parameters
NEW_TP_PCT = 0.15     # was 0.18
NEW_SL_PCT = 0.18     # was 0.25
NEW_MIN_ENTRY = 0.35  # was 0.30
NEW_TIMEOUT = 18      # was 12
NEW_QUANT_MIN = 0.55  # was 0.50
MAKER_FEES = 0.0      # was ~4-7% taker

# 1. Filter: MIN_ENTRY_PRICE = 0.35
print("\n1. MIN_ENTRY_PRICE = $0.35 (was $0.30)")
above_35 = conn.execute("""
    SELECT COUNT(*) as n, SUM(pnl_usd) as net, SUM(pnl_usd + fees_paid) as gross,
           SUM(fees_paid) as fees
    FROM trades WHERE entry_price >= 0.35 AND status != 'open'
""").fetchone()
print(f"   Trades passing: {above_35['n']}/{conn.execute('SELECT COUNT(*) as n FROM trades WHERE status != \"open\"').fetchone()['n']}")
print(f"   Net PnL: ${above_35['net'] or 0:+.2f} (with fees)")
print(f"   Gross PnL: ${above_35['gross'] or 0:+.2f} (before fees)")

# 2. With maker orders (zero fees)
print("\n2. MAKER ORDERS (zero fees)")
print(f"   Gross PnL: ${above_35['gross'] or 0:+.2f}")
print(f"   Fees saved: ${above_35['fees'] or 0:.2f}")
print(f"   Net PnL (maker): ${above_35['gross'] or 0:+.2f}")

# 3. Combined: MIN_ENTRY=0.35 + maker
print("\n3. COMBINED: MIN_ENTRY=$0.35 + maker orders")
print(f"   Projected Net: ${above_35['gross'] or 0:+.2f}")
print(f"   Improvement vs current ($-239.94): ${above_35['gross'] or 0 - (-239.94):+.2f}")

# 4. What about SL impact?
# With tighter SL (18% vs 25%), stop losses happen sooner with smaller losses
# Historical SL trades at >= 0.35 entry:
sl_above_35 = conn.execute("""
    SELECT COUNT(*) as n, SUM(pnl_usd) as total, AVG(pnl_usd) as avg
    FROM trades WHERE exit_reason = 'stop_loss' AND entry_price >= 0.35
""").fetchone()
tp_above_35 = conn.execute("""
    SELECT COUNT(*) as n, SUM(pnl_usd) as total, AVG(pnl_usd) as avg
    FROM trades WHERE exit_reason = 'take_profit' AND entry_price >= 0.35
""").fetchone()
timeout_above_35 = conn.execute("""
    SELECT COUNT(*) as n, SUM(pnl_usd) as total, AVG(pnl_usd) as avg
    FROM trades WHERE exit_reason = 'timeout' AND entry_price >= 0.35
""").fetchone()
dead_above_35 = conn.execute("""
    SELECT COUNT(*) as n, SUM(pnl_usd) as total
    FROM trades WHERE exit_reason = 'dead_market' AND entry_price >= 0.35
""").fetchone()

print("\n4. EXIT REASON BREAKDOWN (entry >= $0.35):")
print(f"   Take Profit: {tp_above_35['n']} trades, ${tp_above_35['total'] or 0:+.2f}")
print(f"   Stop Loss:   {sl_above_35['n']} trades, ${sl_above_35['total'] or 0:+.2f}")
print(f"   Timeout:     {timeout_above_35['n']} trades, ${timeout_above_35['total'] or 0:+.2f}")
print(f"   Dead Market: {dead_above_35['n']} trades, ${dead_above_35['total'] or 0:+.2f}")

# 5. Estimate tighter SL impact
sl_savings = abs(sl_above_35['total'] or 0) * 0.20
print("\n5. TIGHTER SL IMPACT (18% vs 25%):")
print(f"   Estimated SL savings: ${sl_savings:+.2f} (20% of current SL losses)")

# 6. Extended timeout impact
timeout_savings = abs(timeout_above_35['total'] or 0) * 0.15
print("\n6. EXTENDED TIMEOUT IMPACT (18 min vs 12):")
print(f"   Estimated timeout improvement: ${timeout_savings:+.2f} (15% of timeout losses)")

# 7. Total projection
gross = above_35['gross'] or 0
projected = gross + sl_savings + timeout_savings
print(f"\n{'='*70}")
print("TOTAL PROFITABILITY PROJECTION")
print(f"{'='*70}")
print(f"  Gross PnL (entry >= $0.35, maker): ${gross:+.2f}")
print(f"  + Tighter SL savings:               ${sl_savings:+.2f}")
print(f"  + Extended timeout improvement:      ${timeout_savings:+.2f}")
print("  ─────────────────────────────────────────────")
print(f"  PROJECTED NET PNL:                   ${projected:+.2f}")
print("  vs CURRENT NET PNL:                  $-239.94")
print(f"  IMPROVEMENT:                         ${projected - (-239.94):+.2f}")

# 8. Per-trade metrics
trades = above_35['n']
if trades > 0:
    print(f"\n  Per-trade avg:  ${projected/trades:+.2f}")
    print(f"  Trades:         {trades}")
    print("  Win rate needed for breakeven: ", end="")
    wins = conn.execute("SELECT AVG(pnl_usd) as avg FROM trades WHERE pnl_usd > 0 AND entry_price >= 0.35").fetchone()["avg"] or 0
    losses = conn.execute("SELECT AVG(pnl_usd) as avg FROM trades WHERE pnl_usd < 0 AND entry_price >= 0.35").fetchone()["avg"] or 0
    if wins and losses and losses != 0:
        wr_needed = -losses / (wins - losses)
        print(f"{wr_needed:.0%}")

conn.close()
