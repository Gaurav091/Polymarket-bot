"""
Paper-trading dashboard — live view of trades, PnL, survival clock, equity curve.

Reads data/trades.db (WAL) directly; the bot keeps writing while we read.
Auto-refreshes every 2s. No external deps — stdlib http.server + embedded HTML.
"""
from __future__ import annotations

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def get_dashboard_data() -> dict:
    """Everything the dashboard needs, in one query batch."""
    conn = _conn()

    trades = _rows_to_dicts(
        conn.execute(
            """SELECT id, market_question, side, entry_price, exit_price,
                      amount_usd, shares, status, entry_at, exit_at, pnl_usd,
                      edge, classification, materiality, reasoning, headline
               FROM trades ORDER BY id DESC LIMIT 200"""
        ).fetchall()
    )

    closed = conn.execute(
        """SELECT COUNT(*) AS n, COALESCE(SUM(pnl_usd), 0) AS pnl
           FROM trades WHERE status != 'open'"""
    ).fetchone()
    wins = conn.execute(
        "SELECT COUNT(*) AS n FROM trades WHERE pnl_usd > 0"
    ).fetchone()
    losses = conn.execute(
        "SELECT COUNT(*) AS n FROM trades WHERE pnl_usd <= 0 AND status != 'open'"
    ).fetchone()
    open_count = conn.execute(
        """SELECT COUNT(*) AS n, COALESCE(SUM(amount_usd), 0) AS exposure
           FROM trades WHERE status = 'open'"""
    ).fetchone()
    day_pnl = conn.execute(
        """SELECT COALESCE(SUM(pnl_usd), 0) AS pnl FROM trades
           WHERE status != 'open' AND date(exit_at) = date('now')"""
    ).fetchone()
    month_pnl = conn.execute(
        """SELECT COALESCE(SUM(pnl_usd), 0) AS pnl FROM trades
           WHERE status != 'open' AND strftime('%Y-%m', exit_at) = strftime('%Y-%m', 'now')"""
    ).fetchone()

    # Equity curve: cumulative PnL over closed trades, oldest first
    curve = _rows_to_dicts(
        conn.execute(
            """SELECT id, exit_at, pnl_usd FROM trades
               WHERE status != 'open' ORDER BY exit_at ASC LIMIT 500"""
        ).fetchall()
    )

    events = _rows_to_dicts(
        conn.execute(
            "SELECT event, detail, created_at FROM survival_events ORDER BY id DESC LIMIT 50"
        ).fetchall()
    )

    conn.close()

    n = closed["n"]
    return {
        "mode": "PAPER" if config.DRY_RUN else "LIVE",
        "capital": config.CAPITAL_USD,
        "trades": trades,
        "stats": {
            "closed_trades": n,
            "wins": wins["n"],
            "losses": losses["n"],
            "win_rate": round(wins["n"] / n * 100, 1) if n else 0.0,
            "total_pnl": round(float(closed["pnl"]), 2),
            "day_pnl": round(float(day_pnl["pnl"]), 2),
            "month_pnl": round(float(month_pnl["pnl"]), 2),
            "open_positions": open_count["n"],
            "open_exposure": round(float(open_count["exposure"]), 2),
        },
        "equity_curve": curve,
        "survival_events": events,
        "server_time": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }


from .dashboard_page import PAGE



class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/data":
            try:
                data = get_dashboard_data()
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        elif self.path == "/" or self.path == "/index.html":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # silence per-request logging


def main():
    host, port = "127.0.0.1", 8500
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Dashboard: http://{host}:{port}  (Ctrl+C to stop)")
    print("Reading:", config.DB_PATH)
    server.serve_forever()  # type: ignore


if __name__ == "__main__":
    main()
