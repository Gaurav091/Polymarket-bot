"""
Edge detection + position sizing (from PolyAgent's edge.py).

V2 logic: classification direction + materiality → edge → quarter-Kelly sizing.

FEE-AWARE (2026-09): Edge must exceed the expected fee rate after the trade
round-trip. Taker fees peak at ~4-7% of notional at p=0.50. By using maker
orders (limit), fees drop to $0 — but the edge floor still protects against
fallback taker fills.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from . import config
from .calibration import calibrated_probability
from .classifier import Classification
from .markets import Market
from .news import NewsEvent

log = logging.getLogger(__name__)

# Minimum edge after fees — ensures every trade has positive expected value
# even if filled as taker. Polymarket max taker fee rate is 0.07 (crypto),
# peak fee per share at p=0.50 is feeRate * 0.25 ≈ 1.75% per side.
# Round-trip (entry + exit) fee ≈ 3.5%. With edge floor of 0.08, the
# expected profit after fees is edge - round_trip_fee ≈ 4.5%.
MIN_EDGE_AFTER_FEES = 0.08


@dataclass
class Signal:
    market: Market
    market_price: float
    edge: float
    side: str  # "YES" or "NO"
    bet_amount: float
    reasoning: str
    headline: str
    news_source: str
    classification: str
    materiality: float
    total_latency_ms: int = 0
    signal_source: str = "news"  # "news" or "python-quant"


def size_position(edge: float) -> float:
    """Quarter-Kelly sizing, clamped to [MIN_BET, MAX_BET]."""
    kelly = edge / 1.0  # binary market: b=1
    quarter_kelly = max(0.0, kelly) * 0.25 * config.CAPITAL_USD
    return round(min(config.MAX_BET_USD, max(config.MIN_BET_USD, quarter_kelly)), 2)


def _resolve_thresholds(
    emergency_override: bool,
    effective_materiality_threshold: float | None,
    effective_edge_threshold: float | None,
) -> tuple[float, float]:
    """Return (materiality_threshold, edge_threshold) based on override params."""
    if emergency_override:
        return config.EMERGENCY_MATERIALITY_THRESHOLD, config.EMERGENCY_EDGE_THRESHOLD
    if effective_materiality_threshold is not None:
        edge = effective_edge_threshold if effective_edge_threshold is not None else config.EDGE_THRESHOLD
        return effective_materiality_threshold, edge
    return config.MATERIALITY_THRESHOLD, config.EDGE_THRESHOLD


def detect_edge(
    market: Market,
    classification: Classification,
    news_event: NewsEvent,
    emergency_override: bool = False,
    signal_source: str = "news",
    effective_edge_threshold: float | None = None,
    effective_materiality_threshold: float | None = None,
) -> Signal | None:
    """
    Generate a trade signal when:
    - Direction is bullish or bearish (not neutral)
    - Materiality exceeds threshold
    - Market price has room to move in the predicted direction

    In emergency_override mode (survival critical):
    - Materiality threshold drops to EMERGENCY_MATERIALITY_THRESHOLD
    - Edge threshold drops to EMERGENCY_EDGE_THRESHOLD
    """
    if classification.direction == "neutral":
        return None

    materiality_thresh, edge_thresh = _resolve_thresholds(
        emergency_override, effective_materiality_threshold, effective_edge_threshold,
    )
    if classification.materiality < materiality_thresh:
        return None

    # Calibration-adjusted fair probability (favorite-longshot bias correction)
    market_price = calibrated_probability(market.yes_price)
    side, edge = _compute_side_and_edge(
        classification.direction, classification.materiality, market_price, signal_source
    )
    if side is None:
        return None

    entry_price = market_price if side == "YES" else (1.0 - market_price)
    if entry_price < 0.40:
        edge *= 0.60  # cheap-market structural disadvantage discount

    # NO-side sizing penalty: 0% win rate in 20 historical trades.
    # Reduce bet size by 50% for NO trades until proven profitable.
    if side == "NO":
        edge *= 0.50

    if edge < edge_thresh:
        return None

    # Fee-aware guard: even with maker orders, enforce minimum edge floor
    # to protect against fallback taker fills
    if edge < MIN_EDGE_AFTER_FEES:
        return None

    return Signal(
        market=market,
        market_price=market_price,
        edge=round(edge, 4),
        side=side,
        bet_amount=size_position(edge),
        reasoning=classification.reasoning,
        headline=news_event.headline,
        news_source=news_event.source,
        classification=classification.direction,
        materiality=classification.materiality,
        total_latency_ms=classification.latency_ms,
        signal_source=signal_source,
    )


def _compute_side_and_edge(direction: str, materiality: float, market_price: float, signal_source: str = "news") -> tuple[str | None, float]:
    """Compute (side, edge) from direction + price. Returns (None, 0) if invalid.

    ANTI-BEARISH BIAS: Block ALL bearish signals.
    Historical data: 2W/23L on NO trades (8% WR) — systematically wrong.
    Only YES trades (bullish) are profitable: 6W/2L at entry >= 0.78.
    """
    # BLOCK: ALL bearish signals — 8% win rate historically
    if direction == "bearish":
        log.debug(f"[edge] bearish signal blocked (historical 8% WR) — price={market_price:.3f} src={signal_source}")
        return None, 0.0

    if direction == "bullish":
        # Tightened from 0.85 → 0.80: near-certain markets have tiny room to move
        if market_price > 0.80:
            log.debug(f"[edge] bullish blocked: market_price={market_price:.3f} > 0.80 ceiling")
            return None, 0.0
        return "YES", materiality * (1.0 - market_price)
    # NOTE: neutral direction is already blocked upstream (detect_edge returns None)
    # This path (non-bearish, non-bullish) returns NO side with penalty applied upstream
    return "NO", materiality * market_price
