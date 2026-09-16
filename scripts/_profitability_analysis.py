"""Comprehensive trade analysis for profitability improvement."""
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

conn = sqlite3.connect("data/trades.db")
conn.row_factory = sqlite3.Row

# 1. Overall summary
print("=" * 70)
print("TRADE ANALYSIS — PROFITABILITY IMPROVEMENT PLAN")
print("=" * 70)

total = conn.execute("SELECT COUNT(*) as n FROM trades").fetchone()["n"]
closed = conn.execute("SELECT COUNT(*) as n FROM trades WHERE status != 'open'").fetchone()["n"]
open_t = conn.execute("SELECT COUNT(*) as n FROM trades WHERE status = 'open'").fetchone()["n"]

print(f"\nTotal trades: {total} | Closed: {closed} | Open: {open_t}")

# 2. Win/Loss breakdown
wins = conn.execute("SELECT COUNT(*) as n, AVG(pnl_usd) as avg_pnl, SUM(pnl_usd) as total FROM trades WHERE pnl_usd > 0").fetchone()
losses = conn.execute("SELECT COUNT(*) as n, AVG(pnl_usd) as avg_pnl, SUM(pnl_usd) as total FROM trades WHERE pnl_usd < 0").fetchone()
breakeven = conn.execute("SELECT COUNT(*) as n FROM trades WHERE pnl_usd = 0 AND status != 'open'").fetchone()

print(f"\nWins: {wins['n']} trades, avg ${wins['avg_pnl']:.2f}, total ${wins['total']:.2f}")
print(f"Losses: {losses['n']} trades, avg ${losses['avg_pnl']:.2f}, total ${losses['total']:.2f}")
print(f"Breakeven: {breakeven['n']} trades")
print(f"Win rate: {wins['n']/closed*100:.1f}%" if closed else "N/A")

# 3. By exit reason
print(f"\n{'='*70}")
print("BY EXIT REASON")
print(f"{'='*70}")
reasons = conn.execute("""
    SELECT exit_reason, COUNT(*) as n, SUM(pnl_usd) as total, 
           AVG(pnl_usd) as avg, SUM(fees_paid) as fees
    FROM trades WHERE status != 'open' GROUP BY exit_reason ORDER BY total DESC
""").fetchall()
for r in reasons:
    reason = r["exit_reason"] or "unknown"
    net = r["total"] or 0
    fees = r["fees"] or 0
    print(f"  {reason:20s} | {r['n']:3d} trades | PnL=${net:+8.2f} | Fees=${fees:6.2f} | Avg=${r['avg']:+.2f}")

# 4. By side (YES vs NO)
print(f"\n{'='*70}")
print("BY SIDE (YES vs NO)")
print(f"{'='*70}")
for side in ["YES", "NO"]:
    rows = conn.execute("""
        SELECT COUNT(*) as n, SUM(pnl_usd) as total, AVG(pnl_usd) as avg,
               SUM(fees_paid) as fees
        FROM trades WHERE side = ? AND status != 'open'
    """, (side,)).fetchone()
    print(f"  {side:3s} | {rows['n']:3d} trades | PnL=${rows['total'] or 0:+8.2f} | Fees=${rows['fees'] or 0:6.2f} | Avg=${rows['avg'] or 0:+.2f}")

# 5. By entry price range
print(f"\n{'='*70}")
print("BY ENTRY PRICE RANGE")
print(f"{'='*70}")
ranges = [
    ("0.00-0.20", 0, 0.20),
    ("0.20-0.30", 0.20, 0.30),
    ("0.30-0.40", 0.30, 0.40),
    ("0.40-0.50", 0.40, 0.50),
    ("0.50-0.60", 0.50, 0.60),
    ("0.60-0.70", 0.60, 0.70),
    ("0.70-0.80", 0.70, 0.80),
    ("0.80-1.00", 0.80, 1.01),
]
for label, low, high in ranges:
    rows = conn.execute("""
        SELECT COUNT(*) as n, SUM(pnl_usd) as total, AVG(pnl_usd) as avg
        FROM trades WHERE entry_price >= ? AND entry_price < ? AND status != 'open'
    """, (low, high)).fetchone()
    if rows["n"] > 0:
        print(f"  {label:10s} | {rows['n']:3d} trades | PnL=${rows['total'] or 0:+8.2f} | Avg=${rows['avg'] or 0:+.2f}")

# 6. Holding time analysis
print(f"\n{'='*70}")
print("BY HOLDING TIME")
print(f"{'='*70}")
time_ranges = [
    ("< 5 min", 0, 5),
    ("5-10 min", 5, 10),
    ("10-15 min", 10, 15),
    ("15-20 min", 15, 20),
    ("20-30 min", 20, 30),
    ("30+ min", 30, 999),
]
for label, low, high in time_ranges:
    rows = conn.execute("""
        SELECT COUNT(*) as n, SUM(pnl_usd) as total, AVG(pnl_usd) as avg
        FROM trades WHERE holding_minutes >= ? AND holding_minutes < ? AND status != 'open'
    """, (low, high)).fetchone()
    if rows["n"] > 0:
        print(f"  {label:10s} | {rows['n']:3d} trades | PnL=${rows['total'] or 0:+8.2f} | Avg=${rows['avg'] or 0:+.2f}")

# 7. Edge vs outcome
print(f"\n{'='*70}")
print("BY EDGE (CONFIDENCE)")
print(f"{'='*70}")
edge_ranges = [
    ("0-10%", 0, 0.10),
    ("10-20%", 0.10, 0.20),
    ("20-30%", 0.20, 0.30),
    ("30-40%", 0.30, 0.40),
    ("40%+", 0.40, 1.01),
]
for label, low, high in edge_ranges:
    rows = conn.execute("""
        SELECT COUNT(*) as n, SUM(pnl_usd) as total, AVG(pnl_usd) as avg
        FROM trades WHERE edge >= ? AND edge < ? AND status != 'open'
    """, (low, high)).fetchone()
    if rows["n"] > 0:
        print(f"  {label:10s} | {rows['n']:3d} trades | PnL=${rows['total'] or 0:+8.2f} | Avg=${rows['avg'] or 0:+.2f}")

# 8. Top losing trades
print(f"\n{'='*70}")
print("TOP 10 LOSING TRADES")
print(f"{'='*70}")
losers = conn.execute("""
    SELECT id, market_question, side, entry_price, exit_price, pnl_usd, fees_paid, 
           exit_reason, holding_minutes
    FROM trades WHERE pnl_usd < 0 ORDER BY pnl_usd ASC LIMIT 10
""").fetchall()
for r in losers:
    q = (r["market_question"] or "")[:50]
    print(f"  #{r['id']:3d} | {r['side']:3s} @ {r['entry_price']:.3f} | PnL=${r['pnl_usd']:+.2f} | Fees=${r['fees_paid'] or 0:.2f} | {r['exit_reason']}")

# 9. Top winning trades
print(f"\n{'='*70}")
print("TOP 10 WINNING TRADES")
print(f"{'='*70}")
winners = conn.execute("""
    SELECT id, market_question, side, entry_price, exit_price, pnl_usd, fees_paid,
           exit_reason, holding_minutes
    FROM trades WHERE pnl_usd > 0 ORDER BY pnl_usd DESC LIMIT 10
""").fetchall()
for r in winners:
    q = (r["market_question"] or "")[:50]
    print(f"  #{r['id']:3d} | {r['side']:3s} @ {r['entry_price']:.3f} | PnL=${r['pnl_usd']:+.2f} | Fees=${r['fees_paid'] or 0:.2f} | {r['exit_reason']}")

# 10. Fee impact analysis
print(f"\n{'='*70}")
print("FEE IMPACT ANALYSIS")
print(f"{'='*70}")
gross_pnl = conn.execute("SELECT SUM(pnl_usd + fees_paid) as gross FROM trades WHERE fees_paid IS NOT NULL").fetchone()["gross"]
total_fees = conn.execute("SELECT SUM(fees_paid) as fees FROM trades WHERE fees_paid IS NOT NULL").fetchone()["fees"]
net_pnl = conn.execute("SELECT SUM(pnl_usd) as net FROM trades WHERE fees_paid IS NOT NULL").fetchone()["net"]
avg_fee = conn.execute("SELECT AVG(fees_paid) as avg_fee FROM trades WHERE fees_paid IS NOT NULL").fetchone()["avg_fee"]
avg_trade_size = conn.execute("SELECT AVG(amount_usd) as avg_size FROM trades WHERE fees_paid IS NOT NULL").fetchone()["avg_size"]

print(f"Gross PnL (before fees): ${gross_pnl or 0:+.2f}")
print(f"Total fees paid:         ${total_fees or 0:.2f}")
print(f"Net PnL (after fees):    ${net_pnl or 0:+.2f}")
print(f"Average fee per trade:   ${avg_fee or 0:.2f}")
print(f"Average trade size:      ${avg_trade_size or 0:.2f}")
print(f"Fee as % of trade size:  {(total_fees or 0) / (avg_trade_size or 1) / (closed or 1) * 100:.1f}%")

# 11. What would make it profitable?
print(f"\n{'='*70}")
print("PROFITABILITY ANALYSIS")
print(f"{'='*70}")
needed = abs(net_pnl or 0)
print(f"Current net loss: ${abs(net_pnl or 0):.2f}")
print("To break even, need to either:")
print(f"  1. Reduce stop losses by ${needed/2:.2f} total")
print(f"  2. Increase win rate from {wins['n']/closed*100:.1f}% to {(wins['n']+needed/abs(losses['avg_pnl'] or 1))/closed*100:.1f}%")
print(f"  3. Increase avg win from ${wins['avg_pnl'] or 0:.2f} to ${((wins['total'] or 0) + needed)/wins['n']:.2f}")
print(f"  4. Reduce fees by ${total_fees or 0:.2f} (impossible at current rate)")

conn.close()
