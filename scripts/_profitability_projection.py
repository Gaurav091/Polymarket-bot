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

# New parameters (as implemented in fixes)
NEW_TP_PCT = 0.15
NEW_SL_PCT = 0.18
NEW_MIN_ENTRY = 0.45  # was 0.30
NEW_TIMEOUT = 12      # was 15
NEW_QUANT_MIN = 0.75  # was 0.65
MAKER_FEES = 0.0      # maker orders = zero fees

# 1. Filter: MIN_ENTRY_PRICE = 0.45 + NO BEARISH (all sources)
print("\n1. MIN_ENTRY_PRICE = $0.45 + NO BEARISH (was $0.30 + all)")
# Filter trades that would pass our new gates:
# - entry_price >= 0.45
# - classification != 'bearish' (all bearish blocked: 8% WR)
above_45 = conn.execute("""
    SELECT COUNT(*) as n, SUM(pnl_usd) as net, SUM(pnl_usd + fees_paid) as gross,
           SUM(fees_paid) as fees
    FROM trades 
    WHERE entry_price >= 0.45 
    AND classification != 'bearish'
    AND status != 'open'
""").fetchone()
print(f"   Trades passing: {above_45['n']}/{conn.execute('SELECT COUNT(*) as n FROM trades WHERE status != \"open\"').fetchone()['n']}")
print(f"   Net PnL: ${above_45['net'] or 0:+.2f} (with fees)")
print(f"   Gross PnL: ${above_45['gross'] or 0:+.2f} (before fees)")

# 2. With maker orders (zero fees)
print("\n2. MAKER ORDERS (zero fees)")
print(f"   Gross PnL: ${above_45['gross'] or 0:+.2f}")
print(f"   Fees saved: ${above_45['fees'] or 0:.2f}")
print(f"   Net PnL (maker): ${above_45['gross'] or 0:+.2f}")

# 3. Combined: MIN_ENTRY=0.45 + no quant bearish + maker
print("\n3. COMBINED: MIN_ENTRY=$0.45 + no quant bearish + maker orders")
print(f"   Projected Net: ${above_45['gross'] or 0:+.2f}")
print(f"   Improvement vs current ($-239.94): ${above_45['gross'] or 0 - (-239.94):+.2f}")

# Historical SL trades at >= 0.45 entry (excluding ALL bearish):
sl_above_45 = conn.execute("""
    SELECT COUNT(*) as n, SUM(pnl_usd) as total, AVG(pnl_usd) as avg
    FROM trades 
    WHERE exit_reason = 'stop_loss' 
    AND entry_price >= 0.45
    AND classification != 'bearish'
""").fetchone()
tp_above_45 = conn.execute("""
    SELECT COUNT(*) as n, SUM(pnl_usd) as total, AVG(pnl_usd) as avg
    FROM trades 
    WHERE exit_reason = 'take_profit' 
    AND entry_price >= 0.45
    AND classification != 'bearish'
""").fetchone()
timeout_above_45 = conn.execute("""
    SELECT COUNT(*) as n, SUM(pnl_usd) as total, AVG(pnl_usd) as avg
    FROM trades 
    WHERE exit_reason = 'timeout' 
    AND entry_price >= 0.45
    AND classification != 'bearish'
""").fetchone()
dead_above_45 = conn.execute("""
    SELECT COUNT(*) as n, SUM(pnl_usd) as total
    FROM trades 
    WHERE exit_reason = 'dead_market' 
    AND entry_price >= 0.45
    AND classification != 'bearish'
""").fetchone()

print("\n4. EXIT REASON BREAKDOWN (entry >= $0.45, NO BEARISH):")
print(f"   Take Profit: {tp_above_45['n']} trades, ${tp_above_45['total'] or 0:+.2f}")
print(f"   Stop Loss:   {sl_above_45['n']} trades, ${sl_above_45['total'] or 0:+.2f}")
print(f"   Timeout:     {timeout_above_45['n']} trades, ${timeout_above_45['total'] or 0:+.2f}")
print(f"   Dead Market: {dead_above_45['n']} trades, ${dead_above_45['total'] or 0:+.2f}")

# 5. Estimate tighter SL impact + MAX_STOP_LOSS_USD=$3 cap
sl_savings = abs(sl_above_45['total'] or 0) * 0.25  # 25% reduction with tighter SL + dollar cap
print("\n5. TIGHTER SL IMPACT (18% vs 25% + $3 cap):")
print(f"   Estimated SL savings: ${sl_savings:+.2f} (25% of current SL losses)")

# 6. Reduced timeout impact (12 min vs 15) - faster capital recycling
timeout_savings = abs(timeout_above_45['total'] or 0) * 0.20
print("\n6. REDUCED TIMEOUT IMPACT (12 min vs 15):")
print(f"   Estimated timeout improvement: ${timeout_savings:+.2f} (20% of timeout losses)")

# 7. Dead market prevention (200 share min depth)
dead_prevention = abs(dead_above_45['total'] or 0) * 0.80  # 80% of dead market losses prevented
print("\n7. DEAD MARKET PREVENTION (200 share min depth):")
print(f"   Estimated dead market savings: ${dead_prevention:+.2f} (80% of dead market losses)")

# 8. Total projection
gross = above_45['gross'] or 0
projected = gross + sl_savings + timeout_savings + dead_prevention
print(f"\n{'='*70}")
print("TOTAL PROFITABILITY PROJECTION")
print(f"{'='*70}")
print(f"  Gross PnL (entry >= $0.45, no quant bearish, maker): ${gross:+.2f}")
print(f"  + Tighter SL + $3 cap savings:       ${sl_savings:+.2f}")
print(f"  + Reduced timeout improvement:       ${timeout_savings:+.2f}")
print(f"  + Dead market prevention:            ${dead_prevention:+.2f}")
print("  ─────────────────────────────────────────────")
print(f"  PROJECTED NET PNL:                   ${projected:+.2f}")
print("  vs CURRENT NET PNL:                  $-239.94")
print(f"  IMPROVEMENT:                         ${projected - (-239.94):+.2f}")

# 9. Per-trade metrics
trades = above_45['n']
if trades > 0:
    print(f"\n  Per-trade avg:  ${projected/trades:+.2f}")
    print(f"  Trades:         {trades}")
    print("  Win rate needed for breakeven: ", end="")
    wins = conn.execute("SELECT AVG(pnl_usd) as avg FROM trades WHERE pnl_usd > 0 AND entry_price >= 0.45 AND classification != 'bearish'").fetchone()["avg"] or 0
    losses = conn.execute("SELECT AVG(pnl_usd) as avg FROM trades WHERE pnl_usd < 0 AND entry_price >= 0.45 AND classification != 'bearish'").fetchone()["avg"] or 0
    if wins and losses and losses != 0:
        wr_needed = -losses / (wins - losses)
        print(f"{wr_needed:.0%}")

conn.close()
