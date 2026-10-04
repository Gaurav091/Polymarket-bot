"""Recent-trade analysis: what is the bot doing since the profitability overhaul?

Read-only. Run: .venv\\Scripts\\python.exe scripts\\_recent_analysis.py
"""
import sqlite3
from collections import defaultdict

DB = "data/trades.db"


def fetch():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cols = [r[1] for r in con.execute("PRAGMA table_info(trades)")]
    rows = [dict(r) for r in con.execute("SELECT * FROM trades ORDER BY id")]
    con.close()
    return cols, rows


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def main():
    cols, rows = fetch()
    print("=" * 78)
    print("COLUMNS:", ", ".join(cols))
    print(f"TOTAL ROWS: {len(rows)}")
    if not rows:
        print("No trades in DB.")
        return

    closed = [r for r in rows if (r.get("status") or "").lower() != "open"]
    opened = [r for r in rows if r not in closed]
    print(f"CLOSED: {len(closed)} | OTHER: {len(opened)}")
    print(f"FIRST id={rows[0].get('id')} ts={rows[0].get('ts')}")
    print(f"LAST  id={rows[-1].get('id')} ts={rows[-1].get('ts')}")

    if not closed:
        print("\nNo closed trades yet -- the reset happened recently.")
        print("Open/other trades:")
        for r in opened[-25:]:
            print("  id=%s %s | %s @ %s | qty=%s | ts=%s | reason=%s" % (
                r.get("id"), r.get("market") or r.get("question", "")[:40],
                r.get("side"), r.get("entry_price"), r.get("size") or r.get("qty"),
                r.get("ts"), r.get("exit_reason") or r.get("status")))
        return

    def pnl(r):
        for k in ("pnl", "realized_pnl", "pnl_usd"):
            if r.get(k) is not None:
                return num(r[k])
        return 0.0

    def fee(r):
        for k in ("fee", "fees", "fee_paid", "total_fee"):
            if r.get(k) is not None:
                return num(r[k])
        return 0.0

    gross = sum(pnl(r) + fee(r) for r in closed)
    fees = sum(fee(r) for r in closed)
    net = sum(pnl(r) for r in closed)

    print("\n" + "=" * 78)
    print("PnL TOTALS (all closed)")
    print("=" * 78)
    print(f"  Net PnL (incl fees): ${net:+.2f}")
    print(f"  Fees paid:           ${fees:.2f}")
    print(f"  Gross PnL:           ${gross:+.2f}")

    wins = [r for r in closed if pnl(r) > 0]
    losses = [r for r in closed if pnl(r) < 0]
    print(f"\n  Wins: {len(wins)} (avg ${sum(pnl(r) for r in wins)/len(wins):+.2f})" if wins else "\n  Wins: 0")
    print(f"  Losses: {len(losses)} (avg ${sum(pnl(r) for r in losses)/len(losses):+.2f})" if losses else "  Losses: 0")
    if closed:
        print(f"  Win rate: {len(wins)/len(closed)*100:.1f}%")

    def group(keyfn, title, min_n=2):
        buckets = defaultdict(list)
        for r in closed:
            buckets[keyfn(r)].append(r)
        print("\n" + "=" * 78)
        print(title)
        print("=" * 78)
        for k in sorted(buckets, key=lambda x: str(x)):
            g = buckets[k]
            if len(g) < min_n:
                continue
            gnet = sum(pnl(r) for r in g)
            gfee = sum(fee(r) for r in g)
            print(f"  {str(k):<22} | {len(g):>3} trades | net=${gnet:>+8.2f} "
                  f"| fees=${gfee:>6.2f} | avg=${gnet/len(g):>+6.2f}")

    group(lambda r: r.get("exit_reason") or r.get("status"), "BY EXIT REASON")
    group(lambda r: r.get("side"), "BY SIDE")
    group(lambda r: "no_decision" if r.get("decision") is None
          else str(r.get("decision")), "BY DECISION")

    def price_bucket(r):
        p = num(r.get("entry_price"))
        if p == 0:
            return "unknown"
        lo = int(p * 10) / 10
        return f"{lo:.1f}-{lo+0.1:.1f}"

    group(price_bucket, "BY ENTRY PRICE BUCKET (0.1 wide)")

    print("\n" + "=" * 78)
    print("LAST 20 CLOSED TRADES")
    print("=" * 78)
    for r in closed[-20:]:
        q = (r.get("market") or r.get("question") or "")[:44]
        print(f"  #{r.get('id'):<5} {str(r.get('side')):<4} @ {num(r.get('entry_price')):.3f} "
              f"| net={pnl(r):>+7.2f} fee={fee(r):>5.2f} "
              f"| {str(r.get('exit_reason') or r.get('status')):<14} | {q}")

    print("\n" + "=" * 78)
    print("TOP 8 LOSERS")
    print("=" * 78)
    for r in sorted(closed, key=pnl)[:8]:
        print(f"  #{r.get('id'):<5} {str(r.get('side')):<4} @ {num(r.get('entry_price')):.3f} "
              f"| net={pnl(r):>+7.2f} fee={fee(r):>5.2f} | "
              f"{str(r.get('exit_reason') or r.get('status')):<14} | "
              f"{(r.get('market') or r.get('question') or '')[:34]}")


if __name__ == "__main__":
    main()
