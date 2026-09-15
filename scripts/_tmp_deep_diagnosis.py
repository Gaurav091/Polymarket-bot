"""Deep profit diagnosis — traces the full pipeline from signal to PnL."""
import sqlite3, json

conn = sqlite3.connect("data/trades.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 70)
print("CURRENT STATE (all closed trades)")
print("=" * 70)
cur.execute("""
    SELECT COUNT(*) n,
           COALESCE(SUM(pnl_usd), 0) pnl,
           SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) wins,
           SUM(CASE WHEN pnl_usd <= 0 THEN 1 ELSE 0 END) losses
    FROM trades WHERE status != 'open'
""")
r = cur.fetchone()
n = r["n"] or 0; w = r["wins"] or 0
print(f"Closed: {n}  Wins: {w} ({w/n*100:.1f}%)  Total PnL: ${r['pnl'] or 0:.2f}")

print()
print("=" * 70)
print("PnL BY EXIT REASON")
print("=" * 70)
cur.execute("""
    SELECT exit_reason, COUNT(*) n, SUM(pnl_usd) pnl, AVG(pnl_usd) avg_pnl,
           SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) wins
    FROM trades WHERE status != 'open'
    GROUP BY exit_reason ORDER BY pnl
""")
for r in cur.fetchall():
    wr = (r["wins"] or 0) / r["n"] * 100 if r["n"] else 0
    print(f"  {r['exit_reason'] or 'NULL':<20} n={r['n']:<4} total=${r['pnl'] or 0:>8.2f}  avg=${r['avg_pnl'] or 0:>7.2f}  WR={wr:.0f}%")

print()
print("=" * 70)
print("PnL BY ENTRY PRICE BUCKET (AFTER 15c MIN FIX)")
print("=" * 70)
cur.execute("""
    SELECT CASE
             WHEN entry_price < 0.20 THEN 'a. 15-20c'
             WHEN entry_price < 0.35 THEN 'b. 20-35c'
             WHEN entry_price < 0.50 THEN 'c. 35-50c'
             WHEN entry_price < 0.65 THEN 'd. 50-65c'
             WHEN entry_price < 0.80 THEN 'e. 65-80c'
             ELSE 'f. >80c'
           END bucket,
           COUNT(*) n, SUM(pnl_usd) pnl,
           SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) wins,
           AVG(pnl_usd) avg_pnl
    FROM trades WHERE status != 'open'
    GROUP BY bucket ORDER BY bucket
""")
for r in cur.fetchall():
    wr = (r["wins"] or 0) / r["n"] * 100 if r["n"] else 0
    print(f"  {r['bucket']:<12} n={r['n']:<4} pnl=${r['pnl'] or 0:>8.2f}  WR={wr:>5.1f}%  avg=${r['avg_pnl'] or 0:>6.2f}")

print()
print("=" * 70)
print("EXIT REASON × ENTRY PRICE (the critical matrix)")
print("=" * 70)
cur.execute("""
    SELECT exit_reason,
           CASE WHEN entry_price < 0.35 THEN 'cheap' ELSE 'midexpensive' END tier,
           COUNT(*) n, SUM(pnl_usd) pnl
    FROM trades WHERE status != 'open'
    GROUP BY exit_reason, tier ORDER BY tier, exit_reason
""")
for r in cur.fetchall():
    print(f"  {r['exit_reason'] or 'NULL':<20} {r['tier']:<13} n={r['n']:<4} pnl=${r['pnl'] or 0:>8.2f}")

print()
print("=" * 70)
print("EDGE DISTRIBUTION (is the bot actually finding edge?)")
print("=" * 70)
cur.execute("""
    SELECT exit_reason,
           AVG(edge) avg_edge,
           AVG(CASE WHEN pnl_usd > 0 THEN edge END) avg_edge_win,
           AVG(CASE WHEN pnl_usd <= 0 THEN edge END) avg_edge_loss
    FROM trades WHERE status != 'open' AND edge IS NOT NULL
    GROUP BY exit_reason ORDER BY avg_edge
""")
for r in cur.fetchall():
    print(f"  {r['exit_reason'] or 'NULL':<20} avg_edge={r['avg_edge'] or 0:.4f}  win_edge={r['avg_edge_win'] or 0:.4f}  loss_edge={r['avg_edge_loss'] or 0:.4f}")

print()
print("=" * 70)
print("HOLDING TIME DISTRIBUTION (winners vs losers)")
print("=" * 70)
cur.execute("""
    SELECT exit_reason,
           AVG(holding_minutes) avg_hold,
           MIN(holding_minutes) min_hold,
           MAX(holding_minutes) max_hold
    FROM trades WHERE status != 'open' AND holding_minutes IS NOT NULL
    GROUP BY exit_reason ORDER BY avg_hold
""")
for r in cur.fetchall():
    print(f"  {r['exit_reason'] or 'NULL':<20} avg={r['avg_hold'] or 0:>6.1f}min  min={r['min_hold'] or 0:.1f}  max={r['max_hold'] or 0:.1f}")

print()
print("=" * 70)
print("SIGNAL SOURCE × EXIT (is the quant engine the problem?)")
print("=" * 70)
cur.execute("""
    SELECT signal_source, exit_reason, COUNT(*) n, SUM(pnl_usd) pnl,
           AVG(pnl_usd) avg_pnl
    FROM trades WHERE status != 'open'
    GROUP BY signal_source, exit_reason ORDER BY signal_source, pnl
""")
for r in cur.fetchall():
    print(f"  {str(r['signal_source']):<15} {r['exit_reason'] or 'NULL':<20} n={r['n']:<4} pnl=${r['pnl'] or 0:>8.2f}  avg=${r['avg_pnl'] or 0:.2f}")

print()
print("=" * 70)
print("RECENT 30 CLOSED TRADES (ordered by time)")
print("=" * 70)
cur.execute("""
    SELECT id, side, entry_price, exit_price, pnl_usd, exit_reason,
           holding_minutes, signal_source, edge, amount_usd
    FROM trades WHERE status != 'open'
    ORDER BY exit_at DESC LIMIT 30
""")
for r in cur.fetchall():
    side = r["side"]
    entry = r["entry_price"]
    exit_ = r["exit_price"] or 0
    pnl = r["pnl_usd"] or 0
    marker = "W" if pnl > 0 else "L"
    print(f"  [{marker}] #{r['id']} {side:<3} in={entry:.3f} out={exit_:.3f} pnl=${pnl:>6.2f}  {r['exit_reason'] or '?':<15} hold={r['holding_minutes'] or 0:.0f}m  edge={r['edge'] or 0:.4f}  ${r['amount_usd']}")

conn.close()
