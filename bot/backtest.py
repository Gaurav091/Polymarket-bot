"""
Backtest engine — validate the strategy against historical resolved markets.

Replays resolved markets through the classifier and edge engine to produce
a signal quality report. No LLM calls unless classification model is set.

Usage:
    python -m bot.backtest              # full report
    python -m bot.backtest --limit 20   # quick smoke test
    python -m bot.backtest --category crypto
"""
from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from . import config
from . import http
from .calibration import calibrated_probability, is_resolved
from .classifier import classify, Classification
from .edge import detect_edge, Signal
from .markets import Market
from .news import NewsEvent

log = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"


@dataclass
class BacktestResult:
    question: str
    entry_price: float
    exit_price: float
    side: str
    pnl: float
    correct: bool
    edge: float
    materiality: float
    classification: str


@dataclass
class BacktestReport:
    markets_tested: int
    signals_generated: int
    trades_simulated: int
    total_pnl: float
    win_rate: float
    avg_materiality: float
    results: list[BacktestResult]


def fetch_resolved_markets(limit: int = 50, _category: Optional[str] = None) -> list[dict]:
    """Fetch closed markets from Gamma API with volume and outcome prices."""
    params = {"limit": limit, "closed": "true", "order": "volume", "ascending": "false"}
    try:
        resp = http.get(GAMMA_API + "/markets", params=params, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
        markets_raw = raw if isinstance(raw, list) else raw.get("data", [])
    except Exception:
        log.exception("[backtest] Failed to fetch markets")
        return []

    results = []
    for m in markets_raw:
        parsed = _parse_market(m)
        if parsed:
            results.append(parsed)
    return results


def _parse_market(m: dict) -> Optional[dict]:
    """Parse a single raw market dict into our internal format. Returns None on failure."""
    try:
        op = m.get("outcomePrices", "")
        prices = json.loads(op) if isinstance(op, str) else (op or [])
        if not prices or len(prices) < 2:
            return None

        yes_price = float(prices[0])
        resolved_yes = 1.0 if yes_price > 0.5 else 0.0

        return {
            "question": m.get("question", ""),
            "condition_id": m.get("conditionId", ""),
            "yes_price": yes_price,
            "resolved_yes": resolved_yes,
            "volume": float(m.get("volume", 0) or 0),
            "end_date": m.get("endDate", ""),
            "tokens": m.get("tokens", []),
        }
    except (ValueError, TypeError, KeyError):
        return None


def _pnl(side: str, entry: float, resolved: float, bet: float) -> float:
    """Simulate PnL for one trade."""
    if side == "YES":
        return bet if resolved > entry else -bet
    else:
        return bet if resolved < (1 - entry) else -bet


def run_backtest(limit: int = 30, _category: Optional[str] = None) -> BacktestReport:
    """
    Run backtest against the most recently resolved niche markets.

    For each market: generate a synthetic headline from the question,
    run it through classify + detect_edge, simulate a trade at entry_price=0.50.
    """
    log.info(f"[backtest] Fetching last {limit} resolved niche markets...")
    resolved = fetch_resolved_markets(limit=limit)

    if not resolved:
        return BacktestReport(0, 0, 0, 0.0, 0.0, 0.0, [])

    log.info(f"[backtest] Testing {len(resolved)} markets...")
    results: list[BacktestResult] = []
    signals = 0
    total_pnl = 0.0

    for i, m in enumerate(resolved):
        question = m["question"]
        resolved_price = m["resolved_yes"]  # 0.0 or 1.0
        entry_price = 0.50  # conservative midpoint assumption

        market = Market(
            condition_id=m["condition_id"],
            question=question,
            slug="",
            yes_price=entry_price,
            no_price=1 - entry_price,
            volume=m["volume"],
            end_date=m["end_date"],
            tokens=m.get("tokens", []),
        )

        # Synthetic headline derived from the question
        headline = f"Breaking: '{question}' outcome appears to be resolving"
        event = NewsEvent(
            headline=headline,
            source="backtest",
            url="",
            received_at=datetime.now(timezone.utc),
        )

        try:
            classification = classify(headline, market, source="backtest")
        except Exception as e:
            log.debug(f"[backtest] classify error: {e}")
            classification = Classification("neutral", 0.0, "", 0, "backtest-error")

        if classification.direction == "neutral":
            continue

        signals += 1

        side = "YES" if classification.direction == "bullish" else "NO"
        # Edge detection using the actual resolved price as current price
        signal = detect_edge(market, classification, event, emergency_override=False)
        if signal is None:
            continue

        bet = signal.bet_amount
        pnl = _pnl(side, entry_price, resolved_price, bet)
        total_pnl += pnl
        correct = (pnl > 0)

        results.append(BacktestResult(
            question=question[:80],
            entry_price=entry_price,
            exit_price=resolved_price,
            side=side,
            pnl=round(pnl, 2),
            correct=correct,
            edge=signal.edge,
            materiality=classification.materiality,
            classification=classification.direction,
        ))

        if (i + 1) % 10 == 0:
            log.info(f"[backtest] {i + 1}/{len(resolved)} markets processed...")

        time.sleep(0.25)  # rate-limit protection

    wins = sum(1 for r in results if r.correct)
    wr = (wins / len(results) * 100) if results else 0.0
    avg_mat = sum(r.materiality for r in results) / len(results) if results else 0.0

    report = BacktestReport(
        markets_tested=len(resolved),
        signals_generated=signals,
        trades_simulated=len(results),
        total_pnl=round(total_pnl, 2),
        win_rate=round(wr, 1),
        avg_materiality=round(avg_mat * 100, 1),
        results=results,
    )

    _print_report(report)
    return report


def _print_report(r: BacktestReport):
    pnl_str = f"+${r.total_pnl:.2f}" if r.total_pnl >= 0 else f"-${abs(r.total_pnl):.2f}"
    wr_str = f"{r.win_rate:.1f}%"
    print()
    print("=" * 60)
    print("  BACKTEST REPORT")
    print("=" * 60)
    print(f"  Markets tested:      {r.markets_tested}")
    print(f"  Signals generated:   {r.signals_generated}")
    print(f"  Trades simulated:    {r.trades_simulated}")
    print(f"  Total PnL:           {pnl_str}")
    print(f"  Win rate:            {wr_str}")
    print(f"  Avg materiality:     {r.avg_materiality:.1f}%")
    print("=" * 60)
    if r.results:
        print()
        print(f"  {'Question':<45} {'Signal':>8} {'Mat':>5} {'PnL':>8}")
        print(f"  {'-'*45} {'-'*8} {'-'*5} {'-'*8}")
        for res in r.results[:15]:
            p = f"+${res.pnl:.2f}" if res.pnl >= 0 else f"-${abs(res.pnl):.2f}"
            print(f"  {res.question[:45]:<45} {res.classification:>8} {res.materiality:>5.2f} {p:>8}")
        if len(r.results) > 15:
            print(f"  ... and {len(r.results) - 15} more")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backtest the survival bot strategy")
    parser.add_argument("--limit", type=int, default=30, help="Number of resolved markets to test")
    args = parser.parse_args()
    run_backtest(limit=args.limit)
