"""
Journal statistics & analytics — extracted from journal.py.

Contains: segment stats, recent results, trade history queries.
Core trade logging stays in journal.py (smaller surface for edits).
"""
from __future__ import annotations

import sqlite3

from . import config


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_segment_stats(
    signal_source: str | None = None,
    min_trades: int = 3,
) -> dict:
    """Return win_rate, avg_pnl, count for closed trades optionally filtered."""
    conn = _conn()
    base = "status != 'open'"
    args: list = []
    if signal_source:
        base += " AND signal_source = ?"
        args.append(signal_source)
    rows = conn.execute(
        f"""SELECT pnl_usd, tp_hit, sl_hit, holding_minutes,
                   materiality, edge, exit_reason
            FROM trades WHERE {base} ORDER BY exit_at DESC""",
        args,
    ).fetchall()
    conn.close()

    if len(rows) < min_trades:
        return {"count": len(rows), "win_rate": None, "avg_pnl": 0.0,
                "tp_rate": None, "sl_rate": None, "avg_holding": None}

    wins = sum(1 for r in rows if r["pnl_usd"] is not None and r["pnl_usd"] > 0)
    tp = sum(1 for r in rows if r["tp_hit"])
    sl = sum(1 for r in rows if r["sl_hit"])
    holdings = [r["holding_minutes"] for r in rows if r["holding_minutes"] is not None]

    return {
        "count": len(rows),
        "win_rate": wins / len(rows),
        "avg_pnl": sum(r["pnl_usd"] or 0 for r in rows) / len(rows),
        "tp_rate": tp / len(rows),
        "sl_rate": sl / len(rows),
        "avg_holding": sum(holdings) / len(holdings) if holdings else None,
    }


def get_recent_trades(n: int = 20) -> list[dict]:
    """Return recent closed trades with all learner-relevant fields."""
    conn = _conn()
    rows = conn.execute(
        """SELECT id, signal_source, pnl_usd, edge, materiality,
                  tp_hit, sl_hit, holding_minutes, exit_reason, side,
                  market_id, entry_price, exit_price
           FROM trades WHERE status != 'open'
           ORDER BY exit_at DESC LIMIT ?""",
        (n,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_month_pnl() -> float:
    conn = _conn()
    row = conn.execute(
        """SELECT COALESCE(SUM(pnl_usd), 0) AS pnl FROM trades
           WHERE status != 'open' AND strftime('%Y-%m', exit_at) = strftime('%Y-%m', 'now')"""
    ).fetchone()
    conn.close()
    return float(row["pnl"])


def get_recent_results(limit: int = 5) -> list[str]:
    """Recent win/loss sequence for dynamic position sizing."""
    conn = _conn()
    rows = conn.execute(
        """SELECT pnl_usd FROM trades WHERE status != 'open'
           ORDER BY exit_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return ["win" if r["pnl_usd"] > 0 else "loss" for r in rows]


def get_stats() -> dict:
    conn = _conn()
    total = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(pnl_usd), 0) AS pnl FROM trades WHERE status != 'open'"
    ).fetchone()
    wins = conn.execute(
        "SELECT COUNT(*) AS n FROM trades WHERE pnl_usd > 0"
    ).fetchone()
    conn.close()
    n = total["n"]
    return {
        "closed_trades": n,
        "total_pnl": float(total["pnl"]),
        "win_rate": (wins["n"] / n * 100) if n else 0.0,
    }


def get_market_loss_counts(limit: int = 3) -> dict[str, int]:
    """Markets with >= limit closed losses — per-market circuit breaker."""
    conn = _conn()
    rows = conn.execute(
        "SELECT market_id, COUNT(*) AS losses FROM trades "
        "WHERE status != 'open' AND pnl_usd < 0 "
        "GROUP BY market_id HAVING losses >= ?",
        (limit,),
    ).fetchall()
    conn.close()
    return {r["market_id"]: r["losses"] for r in rows}


def get_recently_closed_market_ids(minutes: int = 8) -> set[str]:
    """Markets closed within the last N minutes — cooldown blocks re-entry."""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    conn = _conn()
    rows = conn.execute(
        "SELECT market_id, exit_at FROM trades WHERE status != 'open' "
        "ORDER BY exit_at DESC LIMIT 50"
    ).fetchall()
    conn.close()
    recent: set[str] = set()
    for r in rows:
        try:
            exited = datetime.fromisoformat(r["exit_at"])
        except (ValueError, TypeError):
            continue
        if exited.tzinfo is None:
            exited = exited.replace(tzinfo=timezone.utc)
        if exited >= cutoff:
            recent.add(r["market_id"])
    return recent


def get_day_pnl() -> float:
    conn = _conn()
    row = conn.execute(
        """SELECT COALESCE(SUM(pnl_usd), 0) AS pnl FROM trades
           WHERE status != 'open' AND date(exit_at) = date('now')"""
    ).fetchone()
    conn.close()
    return float(row["pnl"])


