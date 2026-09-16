"""Analyze last 20 closed trades with full detail + SL root-cause analysis."""
import sqlite3
from pathlib import Path
from datetime import datetime

DB = Path(__file__).resolve().parent.parent / "data" / "trades.db"
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

# === LAST 20 CLOSED TRADES ===
rows = conn.execute(
    "SELECT * FROM trades WHERE status != 'open' ORDER BY entry_at DESC LIMIT 20"
).fetchall()

print("=" * 80)
print("LAST 20 CLOSED TRADES (newest first)")
print("=" * 80)

for i, r in enumerate(rows):
    ep = r["entry_price"] or 0
    xp = r["exit_price"] or 0
    pnl = r["pnl_usd"] or 0
    edge = r["edge"] or 0
    mat = r["materiality"] or 0
    hm = r["holding_minutes"] or 0
    src = r["signal_source"] or "?"
    er = r["exit_reason"] or "?"
    cls = r["classification"] or "?"
    amt = r["amount_usd"] or 0
    q = (r["market_question"] or "")[:60]

    tag = "WIN " if pnl > 0 else "LOSS" if pnl < 0 else "BE  "
    print(f"\n#{i+1:2d} [{tag}] ${pnl:+.2f} | {er}")
    print(f"     Market: {q}")
    print(f"     Side: {r['side']} | Source: {src} | Class: {cls}")
    print(f"     Entry: {ep:.3f} -> Exit: {xp:.3f} | Edge: {edge:.1%} | Mat: {mat:.2f}")
    print(f"     Bet: ${amt:.2f} | Hold: {hm:.0f}min")

# === ALL SL HITS (deeper analysis) ===
print("\n" + "=" * 80)
print("ALL STOP LOSS HITS — ROOT CAUSE ANALYSIS")
print("=" * 80)

sl_rows = conn.execute(
    "SELECT * FROM trades WHERE exit_reason='stop_loss' ORDER BY entry_at"
).fetchall()

print(f"\nTotal SL hits: {len(sl_rows)}")

# Bucket by entry price
print("\n--- SL by Entry Price ---")
price_buckets = {}
for r in sl_rows:
    ep = r["entry_price"] or 0
    if ep < 0.10:
        bk = "<0.10"
    elif ep < 0.20:
        bk = "0.10-0.20"
    elif ep < 0.30:
        bk = "0.20-0.30"
    elif ep < 0.50:
        bk = "0.30-0.50"
    elif ep < 0.70:
        bk = "0.50-0.70"
    else:
        bk = "0.70+"
    if bk not in price_buckets:
        price_buckets[bk] = {"count": 0, "total_loss": 0.0, "total_amt": 0.0}
    price_buckets[bk]["count"] += 1
    price_buckets[bk]["total_loss"] += r["pnl_usd"] or 0
    price_buckets[bk]["total_amt"] += r["amount_usd"] or 0

for bk in sorted(price_buckets.keys()):
    d = price_buckets[bk]
    avg_loss = d["total_loss"] / d["count"] if d["count"] else 0
    print(f"  {bk:12} | {d['count']:3} SLs | Total loss: ${d['total_loss']:.2f} | Avg: ${avg_loss:.2f}")

# Bucket by source
print("\n--- SL by Signal Source ---")
src_buckets = {}
for r in sl_rows:
    src = r["signal_source"] or "unknown"
    if src not in src_buckets:
        src_buckets[src] = {"count": 0, "total_loss": 0.0}
    src_buckets[src]["count"] += 1
    src_buckets[src]["total_loss"] += r["pnl_usd"] or 0

for src, d in sorted(src_buckets.items(), key=lambda x: -x[1]["count"]):
    avg = d["total_loss"] / d["count"] if d["count"] else 0
    print(f"  {src:15} | {d['count']:3} SLs | Total: ${d['total_loss']:.2f} | Avg: ${avg:.2f}")

# Bucket by edge
print("\n--- SL by Edge Range ---")
edge_buckets = {}
for r in sl_rows:
    edge = r["edge"] or 0
    if edge < 0.10:
        bk = "<10%"
    elif edge < 0.20:
        bk = "10-20%"
    elif edge < 0.30:
        bk = "20-30%"
    elif edge < 0.50:
        bk = "30-50%"
    else:
        bk = "50%+"
    if bk not in edge_buckets:
        edge_buckets[bk] = {"count": 0, "total_loss": 0.0}
    edge_buckets[bk]["count"] += 1
    edge_buckets[bk]["total_loss"] += r["pnl_usd"] or 0

for bk in sorted(edge_buckets.keys()):
    d = edge_buckets[bk]
    print(f"  {bk:12} | {d['count']:3} SLs | Total: ${d['total_loss']:.2f}")

# Bucket by hold time
print("\n--- SL by Hold Time ---")
time_buckets = {}
for r in sl_rows:
    hm = r["holding_minutes"] or 0
    if hm < 1:
        bk = "<1min"
    elif hm < 3:
        bk = "1-3min"
    elif hm < 6:
        bk = "3-6min"
    elif hm < 12:
        bk = "6-12min"
    else:
        bk = "12+min"
    if bk not in time_buckets:
        time_buckets[bk] = {"count": 0, "total_loss": 0.0}
    time_buckets[bk]["count"] += 1
    time_buckets[bk]["total_loss"] += r["pnl_usd"] or 0

for bk in sorted(time_buckets.keys()):
    d = time_buckets[bk]
    avg = d["total_loss"] / d["count"] if d["count"] else 0
    print(f"  {bk:12} | {d['count']:3} SLs | Total: ${d['total_loss']:.2f} | Avg: ${avg:.2f}")

# Repeat-offender markets
print("\n--- Repeat Offender Markets (SL'd >1x) ---")
market_sl = {}
for r in sl_rows:
    mid = r["market_id"]
    q = (r["market_question"] or "")[:45]
    if mid not in market_sl:
        market_sl[mid] = {"count": 0, "total_loss": 0.0, "question": q}
    market_sl[mid]["count"] += 1
    market_sl[mid]["total_loss"] += r["pnl_usd"] or 0

repeats = {k: v for k, v in market_sl.items() if v["count"] > 1}
for mid, d in sorted(repeats.items(), key=lambda x: -x[1]["count"]):
    print(f"  {d['count']}x SL | ${d['total_loss']:.2f} | {d['question']}")

# ICE loop specifically
print("\n--- ICE LOOP DEEP DIVE ---")
ice_rows = conn.execute(
    "SELECT entry_price, exit_price, pnl_usd, amount_usd, entry_at, exit_at "
    "FROM trades WHERE market_question LIKE '%ICE to NICE%' ORDER BY entry_at"
).fetchall()
if ice_rows:
    total_loss = sum(r["pnl_usd"] or 0 for r in ice_rows)
    total_bet = sum(r["amount_usd"] or 0 for r in ice_rows)
    print(f"  Trades: {len(ice_rows)} | Total bet: ${total_bet:.2f} | Total loss: ${total_loss:.2f}")
    print(f"  Pattern: {ice_rows[0]['entry_price']:.3f} -> {ice_rows[0]['exit_price']:.3f} on EVERY trade")
    first = datetime.fromisoformat(ice_rows[0]["entry_at"])
    last = datetime.fromisoformat(ice_rows[-1]["entry_at"])
    span_hours = (last - first).total_seconds() / 3600
    print(f"  Time span: {first} to {last} ({span_hours:.1f} hours)")
    print(f"  Average bet: ${total_bet/len(ice_rows):.2f}")

# Did MARKET_LOSS_LIMIT fire?
print("\n--- MARKET_LOSS_LIMIT CHECK ---")
print("  If ICE hit 28 SLs, the breaker was NOT installed yet (added in config).")
print("  Current MARKET_LOSS_LIMIT=2 should block after 2 losses on same market.")
print("  VERIFY: Check logs for 'circuit breaker' or 'market limit' messages.")

conn.close()
