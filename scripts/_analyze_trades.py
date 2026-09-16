"""Analyze all closed trades from the journal DB."""
import sqlite3
from pathlib import Path
from datetime import datetime

DB = Path(__file__).resolve().parent.parent / "data" / "trades.db"
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

trades = conn.execute("SELECT * FROM trades ORDER BY entry_at").fetchall()
open_trades = [t for t in trades if t["status"] == "open"]
closed_trades = [t for t in trades if t["status"] != "open"]

print("=== TRADE SUMMARY ===")
print(f"Total trades: {len(trades)}")
print(f"Open trades: {len(open_trades)}")
print(f"Closed trades: {len(closed_trades)}")

if not closed_trades:
    print("No closed trades yet.")
    conn.close()
    exit()

pnls = [float(t["pnl_usd"]) for t in closed_trades]
wins = [p for p in pnls if p > 0]
losses = [p for p in pnls if p <= 0]

print(f"\nTotal PnL: ${sum(pnls):.2f}")
print(f"Win rate: {len(wins)/len(pnls)*100:.1f}%")
print(f"Avg PnL per trade: ${sum(pnls)/len(pnls):.2f}")
if wins:
    print(f"Avg win: ${sum(wins)/len(wins):.2f}")
if losses:
    print(f"Avg loss: ${sum(losses)/len(losses):.2f}")
if losses:
    print(f"Profit factor: {sum(wins)/abs(sum(losses)):.2f}")

# Hold time
hold_times = []
for t in closed_trades:
    try:
        opened = datetime.fromisoformat(t["entry_at"])
        closed_dt = datetime.fromisoformat(t["exit_at"])
        hold_times.append((closed_dt - opened).total_seconds() / 60)
    except Exception:
        pass

if hold_times:
    print(f"Avg hold time: {sum(hold_times)/len(hold_times):.1f} min")
    print(f"Median hold time: {sorted(hold_times)[len(hold_times)//2]:.1f} min")

# By source
print("\n=== BY SOURCE ===")
sources = {}
for t in closed_trades:
    src = t["signal_source"] or "unknown"
    if src not in sources:
        sources[src] = {"trades": 0, "pnl": 0.0, "wins": 0}
    sources[src]["trades"] += 1
    sources[src]["pnl"] += float(t["pnl_usd"])
    if float(t["pnl_usd"]) > 0:
        sources[src]["wins"] += 1

for src, data in sorted(sources.items(), key=lambda x: -x[1]["pnl"]):
    wr = data["wins"]/data["trades"]*100 if data["trades"] else 0
    print(f"  {src:12} | {data['trades']:3} trades | PnL: ${data['pnl']:+.2f} | WR: {wr:.0f}%")

# By side
print("\n=== BY SIDE ===")
sides = {}
for t in closed_trades:
    side = t["side"] or "unknown"
    if side not in sides:
        sides[side] = {"trades": 0, "pnl": 0.0, "wins": 0}
    sides[side]["trades"] += 1
    sides[side]["pnl"] += float(t["pnl_usd"])
    if float(t["pnl_usd"]) > 0:
        sides[side]["wins"] += 1

for side, data in sorted(sides.items(), key=lambda x: -x[1]["pnl"]):
    wr = data["wins"]/data["trades"]*100 if data["trades"] else 0
    print(f"  {side:5} | {data['trades']:3} trades | PnL: ${data['pnl']:+.2f} | WR: {wr:.0f}%")

# By entry price bucket
print("\n=== BY ENTRY PRICE BUCKET ===")
buckets = {"<0.20": [], "0.20-0.30": [], "0.30-0.50": [], "0.50-0.70": [], "0.70-1.00": []}
for t in closed_trades:
    ep = float(t["entry_price"])
    pnl = float(t["pnl_usd"])
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

for bucket, pnls_b in buckets.items():
    if pnls_b:
        n = len(pnls_b)
        total = sum(pnls_b)
        wr = len([p for p in pnls_b if p > 0]) / n * 100
        print(f"  {bucket:10} | {n:3} trades | PnL: ${total:+.2f} | WR: {wr:.0f}%")
    else:
        print(f"  {bucket:10} | no trades")

# By exit reason
print("\n=== BY EXIT REASON ===")
reasons = {}
for t in closed_trades:
    reason = t["exit_reason"] or "unknown"
    if reason not in reasons:
        reasons[reason] = {"trades": 0, "pnl": 0.0, "wins": 0}
    reasons[reason]["trades"] += 1
    reasons[reason]["pnl"] += float(t["pnl_usd"])
    if float(t["pnl_usd"]) > 0:
        reasons[reason]["wins"] += 1

for reason, data in sorted(reasons.items(), key=lambda x: -x[1]["trades"]):
    wr = data["wins"]/data["trades"]*100 if data["trades"] else 0
    print(f"  {reason:12} | {data['trades']:3} trades | PnL: ${data['pnl']:+.2f} | WR: {wr:.0f}%")

# By classification
print("\n=== BY CLASSIFICATION ===")
classifs = {}
for t in closed_trades:
    cls = t["classification"] or "unknown"
    if cls not in classifs:
        classifs[cls] = {"trades": 0, "pnl": 0.0, "wins": 0}
    classifs[cls]["trades"] += 1
    classifs[cls]["pnl"] += float(t["pnl_usd"])
    if float(t["pnl_usd"]) > 0:
        classifs[cls]["wins"] += 1

for cls, data in sorted(classifs.items(), key=lambda x: -x[1]["pnl"]):
    wr = data["wins"]/data["trades"]*100 if data["trades"] else 0
    print(f"  {cls:12} | {data['trades']:3} trades | PnL: ${data['pnl']:+.2f} | WR: {wr:.0f}%")

# PnL distribution
print("\n=== PnL DISTRIBUTION ===")
print(f"Max win: ${max(pnls):.2f}")
print(f"Max loss: ${min(pnls):.2f}")
print(f"Median PnL: ${sorted(pnls)[len(pnls)//2]:.2f}")

# Top 5 winners and losers
print("\n=== TOP 5 WINNERS ===")
sorted_by_pnl = sorted(closed_trades, key=lambda t: float(t["pnl_usd"]), reverse=True)
for t in sorted_by_pnl[:5]:
    mid = t["market_question"][:40] if t["market_question"] else t["market_id"][:25]
    print(f"  ${float(t['pnl_usd']):+.2f} | {t['side']:3} @ ${float(t['entry_price']):.2f} -> ${float(t['exit_price']):.2f} | {mid}")

print("\n=== TOP 5 LOSERS ===")
for t in sorted_by_pnl[-5:]:
    mid = t["market_question"][:40] if t["market_question"] else t["market_id"][:25]
    print(f"  ${float(t['pnl_usd']):+.2f} | {t['side']:3} @ ${float(t['entry_price']):.2f} -> ${float(t['exit_price']):.2f} | {mid}")

# Market repeat analysis
print("\n=== MARKET REPEATS (traded same market >1x) ===")
market_counts = {}
for t in trades:
    mid = t["market_id"]
    if mid not in market_counts:
        market_counts[mid] = {"count": 0, "pnl": 0.0}
    market_counts[mid]["count"] += 1
    if t["exit_at"] is not None and t["pnl_usd"] is not None:
        market_counts[mid]["pnl"] += float(t["pnl_usd"])

repeats = {k: v for k, v in market_counts.items() if v["count"] > 1}
for mid, data in sorted(repeats.items(), key=lambda x: -x[1]["count"])[:10]:
    q = ""
    try:
        row = conn.execute("SELECT market_question FROM trades WHERE market_id=?", (mid,)).fetchone()
        if row:
            q = row[0][:30]
    except Exception:
        pass
    print(f"  {data['count']}x | PnL: ${data['pnl']:+.2f} | {q or mid[:35]}")

# Edge analysis
print("\n=== EDGE ANALYSIS ===")
edges = [(float(t["edge"]), float(t["pnl_usd"])) for t in closed_trades if t["edge"] is not None]
if edges:
    high_edge = [(e, p) for e, p in edges if e >= 0.15]
    low_edge = [(e, p) for e, p in edges if e < 0.15]
    if high_edge:
        print(f"  Edge >= 15%: {len(high_edge)} trades, PnL: ${sum(p for _, p in high_edge):+.2f}, WR: {len([1 for _,p in high_edge if p>0])/len(high_edge)*100:.0f}%")
    if low_edge:
        print(f"  Edge < 15%:  {len(low_edge)} trades, PnL: ${sum(p for _, p in low_edge):+.2f}, WR: {len([1 for _,p in low_edge if p>0])/len(low_edge)*100:.0f}%")

# Streak analysis
print("\n=== STREAK ANALYSIS ===")
streak = 0
max_win_streak = 0
max_loss_streak = 0
current_streak_type = None
for p in pnls:
    is_win = p > 0
    if current_streak_type is None or is_win == current_streak_type:
        streak += 1
    else:
        if current_streak_type and streak > max_win_streak:
            max_win_streak = streak
        elif not current_streak_type and streak > max_loss_streak:
            max_loss_streak = streak
        streak = 1
    current_streak_type = is_win

if current_streak_type and streak > max_win_streak:
    max_win_streak = streak
elif not current_streak_type and streak > max_loss_streak:
    max_loss_streak = streak

print(f"  Max win streak: {max_win_streak}")
print(f"  Max loss streak: {max_loss_streak}")

# Drawdown
print("\n=== DRAWDOWN ANALYSIS ===")
cumulative = 0
peak = 0
max_dd = 0
for p in pnls:
    cumulative += p
    if cumulative > peak:
        peak = cumulative
    dd = peak - cumulative
    if dd > max_dd:
        max_dd = dd
print(f"  Peak PnL: ${peak:.2f}")
print(f"  Max drawdown from peak: ${max_dd:.2f}")

# Survival events
print("\n=== SURVIVAL STATUS ===")
try:
    deaths = conn.execute("SELECT * FROM survival_events WHERE event='death' ORDER BY ts DESC LIMIT 5").fetchall()
    if deaths:
        for d in deaths:
            print(f"  Death at {d['ts']} — reason: {d.get('reason', 'unknown')}")
    else:
        print("  No death events recorded")
except Exception:
    print("  No survival_events table")

conn.close()
