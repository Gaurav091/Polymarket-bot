"""
SQLite journal — trade log, PnL tracking, survival events (from PolyAgent's logger.py).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT NOT NULL,
            market_question TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            amount_usd REAL NOT NULL,
            shares REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            entry_at TEXT NOT NULL DEFAULT (datetime('now')),
            exit_price REAL,
            exit_at TEXT,
            pnl_usd REAL,
            edge REAL,
            reasoning TEXT,
            headline TEXT,
            news_source TEXT,
            classification TEXT,
            materiality REAL,
            signal_source TEXT,
            holding_minutes REAL,
            tp_hit INTEGER DEFAULT 0,
            sl_hit INTEGER DEFAULT 0,
            exit_reason TEXT
        );

        CREATE TABLE IF NOT EXISTS survival_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            detail TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS kv (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS calibration_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT NOT NULL,
            question TEXT,
            signal_source TEXT,
            predicted_direction TEXT,
            predicted_materiality REAL,
            market_price_at_signal REAL,
            resolved_at TEXT,
            actual_outcome TEXT,
            correct INTEGER,
            logged_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    # Migration: add new columns if they don't exist (old DBs)
    for col, col_type in [
        ("signal_source", "TEXT"),
        ("holding_minutes", "REAL"),
        ("tp_hit", "INTEGER"),
        ("sl_hit", "INTEGER"),
        ("exit_reason", "TEXT"),        ("fees_paid", "REAL"),    ]:
        try:
            conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")
            conn.commit()
        except Exception:
            pass
    conn.close()


# ============================================================
# Trades
# ============================================================

def log_trade_open(
    market_id: str, question: str, side: str, entry_price: float,
    amount_usd: float, shares: float, edge: float, reasoning: str,
    headline: str, news_source: str, classification: str, materiality: float,
    signal_source: str = "news",
) -> int:
    conn = _conn()
    cur = conn.execute(
        """INSERT INTO trades (market_id, market_question, side, entry_price,
           amount_usd, shares, status, edge, reasoning, headline, news_source,
           classification, materiality, signal_source)
           VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?)""",
        (market_id, question, side, entry_price, amount_usd, shares,
         edge, reasoning, headline, news_source, classification, materiality,
         signal_source),
    )
    trade_id = cur.lastrowid
    conn.commit()
    conn.close()
    return trade_id


def log_trade_close(
    trade_id: int,
    exit_yes_price: float,
    status: str,
    entry_row: sqlite3.Row | None = None,
    tp_move: float = 0.0,
    sl_move: float = 0.0,
) -> float:
    """Close a trade, compute PnL. Returns realized PnL in USD.

    exit_yes_price is the market's current YES price. The stored entry_price is
    the price of the side we hold (YES price for YES, 1-yes for NO), so we
    convert the exit to the held side's price before computing PnL.

    Pass entry_row (from get_open_trades) + tp_move/sl_move to enable
    tp_hit/sl_hit tracking and holding_minutes.
    """
    conn = _conn()
    row = entry_row if entry_row else conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    if row is None:
        conn.close()
        return 0.0

    shares = row["shares"]
    entry = row["entry_price"]
    side = row["side"]

    # Convert YES exit price to the held side's price
    exit_held_price = exit_yes_price if side == "YES" else 1.0 - exit_yes_price

    # Gross PnL: bought shares at entry, now worth exit_held_price each
    gross_pnl = (exit_held_price - entry) * shares

    # Polymarket taker fee: fee = shares * feeRate * p * (1-p)
    # Applied on both entry and exit (market orders = taker)
    fr = config.POLY_FEE_RATE
    entry_fee = shares * fr * entry * (1 - entry)
    exit_fee = shares * fr * exit_held_price * (1 - exit_held_price)
    total_fee = entry_fee + exit_fee
    pnl = gross_pnl - total_fee

    # Compute holding_minutes, tp_hit, sl_hit if price path data available
    holding_minutes = None
    tp_hit = 0
    sl_hit = 0
    if entry_row is not None and tp_move > 0 and sl_move > 0:
        try:
            entered = datetime.fromisoformat(row["entry_at"])
            if entered.tzinfo is None:
                entered = entered.replace(tzinfo=timezone.utc)
            holding_minutes = (datetime.now(timezone.utc) - entered).total_seconds() / 60
            move = exit_held_price - entry
            if move >= tp_move:
                tp_hit = 1
            elif move <= -sl_move:
                sl_hit = 1
        except Exception:
            pass

    now_iso = datetime.now(timezone.utc).isoformat()
    if holding_minutes is not None:
        conn.execute(
            """UPDATE trades SET status = ?, exit_price = ?, exit_at = ?,
               pnl_usd = ?, holding_minutes = ?, tp_hit = ?, sl_hit = ?,
               exit_reason = ?, fees_paid = ? WHERE id = ?""",
            (status, exit_held_price, now_iso, pnl, holding_minutes, tp_hit, sl_hit, status, total_fee, trade_id),
        )
    else:
        conn.execute(
            """UPDATE trades SET status = ?, exit_price = ?, exit_at = ?,
               pnl_usd = ?, exit_reason = ?, fees_paid = ? WHERE id = ?""",
            (status, exit_held_price, now_iso, pnl, status, total_fee, trade_id),
        )
    conn.commit()
    conn.close()
    return pnl


def get_open_trades() -> list[sqlite3.Row]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE status = 'open' ORDER BY entry_at"
    ).fetchall()
    conn.close()
    return rows


# ============================================================
# Survival events
# ============================================================

def log_survival_event(event: str, detail: str = ""):
    conn = _conn()
    conn.execute(
        "INSERT INTO survival_events (event, detail) VALUES (?, ?)",
        (event, detail),
    )
    conn.commit()
    conn.close()


# ============================================================
# KV store (peak equity etc.)
# ============================================================

def save_peak_equity(peak: float):
    conn = _conn()
    conn.execute(
        "INSERT OR REPLACE INTO kv (key, value) VALUES ('peak_equity', ?)",
        (str(peak),),
    )
    conn.commit()
    conn.close()


def get_peak_equity() -> float | None:
    conn = _conn()
    row = conn.execute(
        "SELECT value FROM kv WHERE key = 'peak_equity'"
    ).fetchone()
    conn.close()
    return float(row["value"]) if row else None


# ============================================================
# Calibration tracking — delegated to calibration_tracker.py
# ============================================================
from .calibration_tracker import (  # noqa: E402, F401
    log_calibration_signal,
    check_resolved_markets,
    get_calibration_stats,
    get_calibration_recommendation,
)
