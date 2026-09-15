"""
Market scanners — extracted from main.py.

News, quant ensemble, and cross-platform arbitrage scanning.
These are the signal-generation methods pulled out of SurvivalBot
to keep main.py under the 250-line limit.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from . import config
from . import journal
from .calibration import is_resolved
from .classifier import Classification, classify
from .edge import detect_edge
from .kalshi_arb import find_arb_opportunities
from .matcher import match_news_to_markets
from .news import NewsEvent
from .quant import compute_quant_signal, fetch_price_history
from .timesfm_forecast import forecast_batch

log = logging.getLogger(__name__)


def timesfm_scores(scan_markets: list) -> dict:
    """Batched TimesFM forecast — ONE forward pass for all markets."""
    if not config.TIMESFM_ENABLED:
        return {}
    hist_map = {}
    for m in scan_markets:
        token = m.token_id("YES")
        if token:
            hist = fetch_price_history(token)
            if len(hist) >= config.TIMESFM_MIN_HISTORY:
                hist_map[token] = [p for _, p in hist]
    if not hist_map:
        return {}
    return forecast_batch(hist_map)


def quant_signal_for(market, tfm_scores: dict, emergency: bool, learner):
    """Score one market with the ensemble → (edge Signal or None, QuantSignal)."""
    token = market.token_id("YES")
    tfm_score = tfm_scores.get(token) if token else None
    qs = compute_quant_signal(market, timesfm_score=tfm_score)
    if qs.direction == "neutral" or qs.strength < config.QUANT_MIN_STRENGTH:
        return None, qs
    classification = Classification(
        direction=qs.direction,
        materiality=min(0.65, qs.strength * 1.2),
        reasoning=f"quant: mom={qs.momentum} mrev={qs.mean_rev} flow={qs.flow} tfm={qs.timesfm}",
        latency_ms=0,
        model="python-quant",
    )
    event = NewsEvent(
        headline=f"[quant] {market.question}",
        source="quant-engine",
        url="",
        received_at=datetime.now(timezone.utc),
    )
    signal = detect_edge(
        market, classification, event,
        emergency_override=emergency,
        signal_source="python-quant",
        effective_edge_threshold=learner.get_effective_edge_threshold("python-quant"),
        effective_materiality_threshold=learner.get_effective_materiality_threshold("python-quant"),
    )
    return signal, qs


def run_quant_scan(bot):
    """Score tracked markets with the free-data quant ensemble."""
    budget = 40.0
    started = time.time()
    scan_markets = bot.markets[:30]
    tfm_scores = timesfm_scores(scan_markets)
    for market in scan_markets:
        if time.time() - started > budget:
            log.debug("[quant] scan budget exhausted — deferring rest to next cycle")
            break
        try:
            emergency = bot.survival.is_critical()
            signal, qs = quant_signal_for(
                market, tfm_scores, emergency, bot.learner,
            )
            if signal:
                bot.stats["signals"] += 1
                log.info(
                    f"[quant] {qs.direction.upper()} str={qs.strength:.2f} "
                    f"(mom={qs.momentum:+.2f} mrev={qs.mean_rev:+.2f} "
                    f"flow={qs.flow:+.2f} tfm={qs.timesfm:+.2f})"
                    f"{' [EMERGENCY]' if emergency else ''}"
                    f" — \"{market.question[:45]}\""
                )
                bot._maybe_trade(signal)
        except Exception as e:
            log.debug(f"[quant] scan error: {e}")


def run_arb_scan(bot):
    """Check for guaranteed arbitrage between Polymarket and Kalshi."""
    try:
        opps = find_arb_opportunities(bot.markets, min_profit_cents=0.03)
        for opp in opps:
            log.info(
                f"[arb] GUARANTEED {opp.guaranteed_profit_cents:.1f}c: "
                f"{opp.direction} | {opp.polymarket_question[:50]}"
            )
            bot.stats["signals"] += 1
    except Exception as e:
        log.debug(f"[arb] scan error: {e}")


def run_news_scan(bot):
    """Poll news, match to markets, classify, and fire trades."""
    events = bot.news.poll()
    if not events:
        return
    bot.stats["news"] += len(events)
    for event in events:
        matched = match_news_to_markets(event.headline, bot.markets)
        bot.stats["matched"] += len(matched)
        for market in matched[:3]:
            try:
                classification = classify(event.headline, market, event.source)
                if classification.direction == "neutral":
                    continue
                emergency = bot.survival.is_critical()
                signal = detect_edge(
                    market, classification, event,
                    emergency_override=emergency,
                    signal_source="news",
                    effective_edge_threshold=bot.learner.get_effective_edge_threshold("news"),
                    effective_materiality_threshold=bot.learner.get_effective_materiality_threshold("news"),
                )
                if signal is None:
                    continue
                bot.stats["signals"] += 1
                bot._maybe_trade(signal)
            except Exception as e:
                log.warning(f"[pipeline] error: {e}")
