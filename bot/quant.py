"""
Quant engine — Python-native prediction signals from FREE Polymarket data.

Reduces LLM dependency to near-zero. Four signal families:

1. MOMENTUM   — CLOB price history (free /prices-history endpoint):
               short EMA vs long EMA. Trend continuation.
2. MEAN-REV   — z-score of current price vs 7-day distribution.
               Fade extreme moves back toward the mean.
3. FLOW       — live order book imbalance (free /book endpoint):
               bid vs ask depth pressure.
4. ON-CHAIN   — recent trade fills from CLOB (smart money, whale detection):
               who's actually buying/selling right now.

Each returns a score in [-1, +1] (+ = YES more likely, - = NO more likely).
The ensemble combines them with weights; news sentiment (keyword lexicon)
is layered on top only when a matching headline exists.

No LLM calls. No paid APIs. Pure Python + requests.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field

import requests

from . import config
from . import http
from .markets import Market
from .quant_signals import momentum_signal, mean_reversion_signal, flow_signal, _ema  # noqa: F401

log = logging.getLogger(__name__)

CLOB_HOST = "https://clob.polymarket.com"


# ============================================================
# Data fetchers (free endpoints, cached)
# ============================================================

@dataclass
class _CacheEntry:
    data: dict | None
    ts: float


_cache: dict[str, _CacheEntry] = {}
_CACHE_TTL = 120.0  # 2 min


def _cached_get(key: str, url: str, params: dict, ttl: float | None = None, timeout: float = 10.0) -> dict | None:
    entry = _cache.get(key)
    if entry and time.time() - entry.ts < (ttl or _CACHE_TTL):
        return entry.data
    try:
        resp = http.get(url, params=params, timeout=timeout)  # hard-capped in watchdog
        resp.raise_for_status()
        data = resp.json()
        _cache[key] = _CacheEntry(data=data, ts=time.time())
        return data
    except Exception as e:
        log.debug(f"[quant] fetch failed {url}: {e}")
        return None


def fetch_price_history(token_id: str, interval: str = "1w") -> list[tuple[float, float]]:
    """(timestamp, price) series from the free CLOB prices-history endpoint."""
    data = _cached_get(
        f"hist:{token_id}:{interval}",
        f"{CLOB_HOST}/prices-history",
        {"market": token_id, "interval": interval, "fidelity": 60},
        ttl=300.0,
    )
    if not data:
        return []
    return [(p["t"], p["p"]) for p in data.get("history", [])]


def fetch_order_book(token_id: str) -> dict | None:
    """Live order book from the free CLOB /book endpoint."""
    return _cached_get(
        f"book:{token_id}",
        f"{CLOB_HOST}/book",
        {"token_id": token_id},
        ttl=30.0,
    )


# ============================================================
# Signal 1: Momentum (EMA crossover on price history)
# ============================================================

# ============================================================
# Signal 2: Mean reversion (z-score vs recent distribution)
# ============================================================

# ============================================================
# Signal 3: Order book imbalance (flow pressure)
# ============================================================

# ============================================================
# Ensemble
# ============================================================

@dataclass
class QuantSignal:
    direction: str          # "bullish" | "bearish" | "neutral"
    strength: float         # 0.0-1.0 (like materiality)
    momentum: float = 0.0
    mean_rev: float = 0.0
    flow: float = 0.0
    onchain_flow: float = 0.0  # smart money signal from trade fills
    timesfm: float = 0.0    # foundation-model forecast drift
    macro: float = 0.0      # macro regime score (VIX, crypto, SP500)
    sources_used: int = 0


WEIGHTS = {"momentum": 0.30, "mean_rev": 0.10, "flow": 0.15, "onchain": 0.10, "timesfm": 0.15, "macro": 0.20}


def compute_quant_signal(market: Market, timesfm_score: float | None = None) -> QuantSignal:
    """Combine all Python-native signals into one prediction for a market.

    timesfm_score: pre-computed foundation-model drift in [-1, +1], from
    timesfm_forecast.forecast_batch() (caller batches to avoid 13s/market).
    """
    token_id = market.token_id("YES")
    if not token_id:
        return QuantSignal("neutral", 0.0)

    mom = momentum_signal(token_id)
    mrev = mean_reversion_signal(token_id, market.yes_price)
    flow = flow_signal(token_id, market.yes_price)
    tfm = timesfm_score if timesfm_score is not None else 0.0

    # On-chain flow signal (smart money / whale detection)
    onchain = 0.0
    try:
        from .flow import compute_flow_signal
        flow_sig = compute_flow_signal(market)
        onchain = flow_sig.net_direction * flow_sig.confidence
    except Exception:
        pass  # on-chain flow is optional; don't break if it fails

    # Macro regime signal (VIX, crypto, SP500, DeFi TVL)
    macro_score = 0.0
    try:
        from .macro import fetch_macro_context
        ctx = fetch_macro_context()
        macro_score = ctx.regime_score
    except Exception:
        pass  # macro is optional; don't break if it fails

    parts = [
        (mom, WEIGHTS["momentum"]),
        (mrev, WEIGHTS["mean_rev"]),
        (flow, WEIGHTS["flow"]),
        (onchain, WEIGHTS["onchain"]),
        (tfm, WEIGHTS["timesfm"]),
        (macro_score, WEIGHTS["macro"]),
    ]
    used = sum(1 for v, _ in parts if abs(v) > 0.01)
    combined = sum(v * w for v, w in parts)

    strength = min(1.0, abs(combined))
    if strength < 0.15:
        direction = "neutral"
    else:
        direction = "bullish" if combined > 0 else "bearish"

    return QuantSignal(
        direction=direction,
        strength=round(strength, 3),
        momentum=round(mom, 3),
        mean_rev=round(mrev, 3),
        flow=round(flow, 3),
        onchain_flow=round(onchain, 3),
        timesfm=round(tfm, 3),
        macro=round(macro_score, 3),
        sources_used=used,
    )
