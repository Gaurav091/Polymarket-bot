"""Deep analysis of trade patterns — loss leaders, winners, timeout behavior."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "trades.db"
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

# ICE market loss leader
print("=== ICE MARKET (28 trades, -$71.47) ===")
rows = conn.execute(
    "SELECT entry_price, exit_price, pnl_usd, side, exit_reason, signal_source "
    "FROM trades WHERE market_question LIKE '%ICE to NICE%' ORDER BY entry_at"
).fetchall()
for r in rows:
    print(f"  {r['side']:3} @ {r['entry_price']:.2f} -> {r['exit_price']:.2f} "
          f"| PnL: ${r['pnl_usd']:+.2f} | {r['exit_reason']:12} | {r['signal_source']}")

# LCK market big winner
print("\n=== LCK MARKET (9 trades, +$263.10) ===")
rows = conn.execute(
    "SELECT entry_price, exit_price, pnl_usd, side, exit_reason "
    "FROM trades WHERE market_question LIKE '%LCK%' ORDER BY entry_at"
).fetchall()
for r in rows:
    ep = r['entry_price']
    xp = r['exit_price'] if r['exit_price'] else 0.0
    pnl = r['pnl_usd'] if r['pnl_usd'] else 0.0
    er = r['exit_reason'] or 'open'
    print(f"  {r['side']:3} @ {ep:.2f} -> {xp:.2f} | PnL: ${pnl:+.2f} | {er:12}")

# Timeout trades in detail
print("\n=== TIMEOUT TRADES BY PRICE BUCKET ===")
rows = conn.execute(
    "SELECT entry_price, pnl_usd FROM trades WHERE exit_reason='timeout'"
).fetchall()
buckets = {"<0.20": [], "0.20-0.30": [], "0.30-0.50": [], "0.50-0.70": [], "0.70-1.00": []}
for r in rows:
    ep = r["entry_price"]
    pnl = r["pnl_usd"]
    if ep < 0.20:
        buckets["<0.20"].append(pnl)
    elif ep < 0.30:
        buckets["0.20-0.30"].append(pnl)
    elif ep < 0.50:
        buckets["0.30-0.50"].append(pnl)
    elif ep < 0.70:
        buckets["0.50-0.70"].append(pnl)
    else:
        buckets["0.70-1.00"].append(pnl)

for b, ps in buckets.items():
    if ps:
        wr = len([p for p in ps if p > 0]) / len(ps) * 100
        print(f"  {b:10} | {len(ps)} trades | PnL: ${sum(ps):+.2f} | WR: {wr:.0f}%")

# Position sizing
print("\n=== POSITION SIZING ===")
rows = conn.execute('SELECT amount_usd FROM trades WHERE status != "open"').fetchall()
amounts = [float(r[0]) for r in rows]
print(f"Avg bet size: ${sum(amounts)/len(amounts):.2f}")
print(f"Min bet: ${min(amounts):.2f}")
print(f"Max bet: ${max(amounts):.2f}")
print(f"Bets at min ($3): {len([a for a in amounts if abs(a-3.0)<0.01])}")
print(f"Bets at $5+: {len([a for a in amounts if a >= 5.0])}")
print(f"Bets at $10 (max): {len([a for a in amounts if abs(a-10.0)<0.01])}")

# TP trade analysis
print("\n=== TAKE PROFIT TRADES ===")
rows = conn.execute(
    "SELECT entry_price, exit_price, pnl_usd, holding_minutes FROM trades "
    "WHERE exit_reason='take_profit' ORDER BY entry_at"
).fetchall()
for r in rows[:15]:
    hm = f"{r['holding_minutes']:.1f}min" if r["holding_minutes"] else "N/A"
    print(f"  Entry: {r['entry_price']:.2f} -> Exit: {r['exit_price']:.2f} "
          f"| PnL: ${r['pnl_usd']:+.2f} | Hold: {hm}")

# Recent 20 trades
print("\n=== RECENT 20 TRADES ===")
rows = conn.execute(
    "SELECT market_question, entry_price, exit_price, pnl_usd, exit_reason, "
    "side, signal_source FROM trades WHERE status != 'open' ORDER BY entry_at DESC LIMIT 20"
).fetchall()
for r in rows:
    q = (r['market_question'] or '')[:35]
    ep = r['entry_price'] or 0.0
    xp = r['exit_price'] or 0.0
    pnl = r['pnl_usd'] or 0.0
    er = r['exit_reason'] or 'open'
    src = r['signal_source'] or 'unknown'
    print(f"  {r['side']:3} {src:12} | {ep:.2f}->{xp:.2f} | ${pnl:+.2f} | {er:12} | {q}")

# Stop loss analysis - are there patterns in what hits SL?
print("\n=== STOP LOSS TRADES - WHAT GOES WRONG ===")
rows = conn.execute(
    "SELECT market_question, entry_price, exit_price, pnl_usd, side, "
    "signal_source, edge, materiality FROM trades WHERE exit_reason='stop_loss' "
    "ORDER BY entry_at"
).fetchall()
sl_buckets = {'<0.20': [], '0.20-0.30': [], '0.30-0.50': [], '0.50-0.70': [], '0.70-1.00': []}
sl_by_source = {}
for r in rows:
    ep = r['entry_price'] or 0.0
    pnl = r['pnl_usd'] or 0.0
    src = r['signal_source'] or 'unknown'
    if ep < 0.20:
        sl_buckets['<0.20'].append(pnl)
    elif ep < 0.30:
        sl_buckets['0.20-0.30'].append(pnl)
    elif ep < 0.50:
        sl_buckets['0.30-0.50'].append(pnl)
    elif ep < 0.70:
        sl_buckets['0.50-0.70'].append(pnl)
    else:
        sl_buckets['0.70-1.00'].append(pnl)
    if src not in sl_by_source:
        sl_by_source[src] = {'count': 0, 'pnl': 0.0}
    sl_by_source[src]['count'] += 1
    sl_by_source[src]['pnl'] += pnl

print(f"Total SL hits: {len(rows)}")
for b, ps in sl_buckets.items():
    if ps:
        print(f"  {b:10} | {len(ps)} SL hits | Total loss: ${sum(ps):.2f}")
for src, data in sorted(sl_by_source.items(), key=lambda x: -x[1]["count"]):
    print(f"  Source: {src:12} | {data['count']} SL hits | ${data['pnl']:.2f}")

# Edge of winning vs losing trades
print("\n=== EDGE OF WINNERS vs LOSERS ===")
rows = conn.execute(
    "SELECT edge, pnl_usd FROM trades WHERE status != 'open' AND edge IS NOT NULL"
).fetchall()
winner_edges = [r['edge'] for r in rows if (r['pnl_usd'] or 0) > 0]
loser_edges = [r['edge'] for r in rows if (r['pnl_usd'] or 0) <= 0]
if winner_edges:
    print(f"Winners avg edge: {sum(winner_edges)/len(winner_edges)*100:.1f}% (n={len(winner_edges)})")
if loser_edges:
    print(f"Losers avg edge:  {sum(loser_edges)/len(loser_edges)*100:.1f}% (n={len(loser_edges)})")

# Time-based analysis
print("\n=== TRADES BY HOUR (UTC) ===")
rows = conn.execute(
    "SELECT substr(entry_at, 12, 2) as hour, pnl_usd FROM trades WHERE status != 'open'"
).fetchall()
hour_data = {}
for r in rows:
    h = r[0]
    if h not in hour_data:
        hour_data[h] = {"count": 0, "pnl": 0.0}
    hour_data[h]["count"] += 1
    hour_data[h]["pnl"] += r["pnl_usd"]

for h in sorted(hour_data.keys()):
    d = hour_data[h]
    print(f"  UTC {h}:00 | {d['count']:3} trades | PnL: ${d['pnl']:+.2f}")

conn.close()
