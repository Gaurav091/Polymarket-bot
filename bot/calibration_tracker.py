"""
Calibration accuracy tracking — log predictions, check resolutions, report accuracy.

Extracted from journal.py to keep modules under 250 lines.
Uses the same SQLite DB connection as journal.
"""
from __future__ import annotations

import logging
import sqlite3

from . import config

log = logging.getLogger(__name__)


def _conn() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def log_calibration_signal(
    market_id: str,
    question: str,
    signal_source: str,
    predicted_direction: str,
    predicted_materiality: float,
    market_price_at_signal: float,
):
    """Log a signal for later calibration checking.
    
    When the market resolves, check_resolutions() will mark it correct/incorrect.
    """
    conn = _conn()
    conn.execute(
        """INSERT INTO calibration_log 
           (market_id, question, signal_source, predicted_direction,
            predicted_materiality, market_price_at_signal)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (market_id, question, signal_source, predicted_direction,
         predicted_materiality, market_price_at_signal),
    )
    conn.commit()
    conn.close()


def check_resolved_markets() -> int:
    """Check pending calibration entries against resolved markets.
    
    Returns the number of newly resolved entries.
    """
    from .calibration import is_resolved
    from .markets import get_current_price
    
    conn = _conn()
    pending = conn.execute(
        """SELECT id, market_id, predicted_direction, market_price_at_signal
           FROM calibration_log WHERE actual_outcome IS NULL"""
    ).fetchall()
    
    resolved_count = 0
    for row in pending:
        prices = get_current_price(row["market_id"])
        if prices is None:
            continue
        yes_price, no_price = prices
        if not is_resolved(yes_price, no_price):
            continue
        
        actual_outcome = "YES" if yes_price > 0.5 else "NO"
        correct = 1 if actual_outcome == row["predicted_direction"] else 0
        
        conn.execute(
            """UPDATE calibration_log 
               SET actual_outcome = ?, correct = ?, resolved_at = datetime('now')
               WHERE id = ?""",
            (actual_outcome, correct, row["id"]),
        )
        resolved_count += 1
    
    conn.commit()
    conn.close()
    return resolved_count


def get_calibration_stats(
    signal_source: str | None = None,
    min_samples: int = 5,
) -> dict:
    """Get calibration accuracy statistics.
    
    Returns accuracy by source, direction, and overall.
    """
    conn = _conn()
    base = "actual_outcome IS NOT NULL"
    args: list = []
    if signal_source:
        base += " AND signal_source = ?"
        args.append(signal_source)
    
    rows = conn.execute(
        f"""SELECT predicted_direction, correct, signal_source
            FROM calibration_log WHERE {base}""",
        args,
    ).fetchall()
    conn.close()
    
    if len(rows) < min_samples:
        return {"count": len(rows), "accuracy": None, "by_source": {}}
    
    total_correct = sum(r["correct"] for r in rows)
    accuracy = total_correct / len(rows)
    
    by_source: dict[str, dict] = {}
    sources = {r["signal_source"] for r in rows if r["signal_source"]}
    for src in sources:
        src_rows = [r for r in rows if r["signal_source"] == src]
        if len(src_rows) >= 3:
            src_correct = sum(r["correct"] for r in src_rows)
            by_source[src] = {
                "accuracy": src_correct / len(src_rows),
                "count": len(src_rows),
            }
    
    return {
        "count": len(rows),
        "accuracy": accuracy,
        "by_source": by_source,
    }


def get_calibration_recommendation() -> str:
    """Generate a recommendation based on calibration stats.
    
    Returns: "STRONG" / "WEAK" / "PAUSE" / "INSUFFICIENT_DATA"
    """
    stats = get_calibration_stats()
    if stats["accuracy"] is None:
        return "INSUFFICIENT_DATA"
    if stats["accuracy"] >= 0.60:
        return "STRONG"
    if stats["accuracy"] >= 0.50:
        return "WEAK"
    return "PAUSE"
