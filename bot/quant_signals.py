"""
Quant signal functions — extracted from quant.py.

Signal 1: Momentum (EMA crossover on price history)
Signal 2: Mean reversion (z-score vs recent distribution)
Signal 3: Order book imbalance (flow pressure)

Each returns a score in [-1, +1]. No LLM calls. Pure Python + requests.
"""
from __future__ import annotations

import math
import logging
import time
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

CLOB_HOST = "https://clob.polymarket.com"

# Inline fetchers (moved from quant.py to break circular import)
@dataclass
class _CacheEntry:
    data: dict | None
    ts: float


_cache: dict[str, _CacheEntry] = {}
_CACHE_TTL = 120.0


def _cached_get(key: str, url: str, params: dict, ttl: float | None = None, timeout: float = 10.0) -> dict | None:
    entry = _cache.get(key)
    if entry and time.time() - entry.ts < (ttl or _CACHE_TTL):
        return entry.data
    try:
        resp = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
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
        f"history:{token_id}:{interval}",
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

def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    k = 2.0 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def momentum_signal(token_id: str) -> float:
    """Short EMA vs long EMA → [-1, +1]. Positive = upward trend = YES bullish."""
    history = fetch_price_history(token_id)
    if len(history) < 20:
        return 0.0
    prices = [p for _, p in history]
    short_ema = _ema(prices[-12:], 6)
    long_ema = _ema(prices[-48:] if len(prices) >= 48 else prices, 24)
    if long_ema == 0:
        return 0.0
    raw = (short_ema - long_ema) / max(long_ema, 0.05)
    return max(-1.0, min(1.0, raw))


def mean_reversion_signal(token_id: str, current_price: float) -> float:
    """Fade extremes: price far below its mean → positive (buy YES cheap)."""
    history = fetch_price_history(token_id)
    if len(history) < 30:
        return 0.0
    prices = [p for _, p in history]
    mean = sum(prices) / len(prices)
    var = sum((p - mean) ** 2 for p in prices) / len(prices)
    std = math.sqrt(var)
    if std < 1e-6:
        return 0.0
    z = (current_price - mean) / std
    # Invert: stretched high → expect pull down (bearish), stretched low → bullish
    return max(-1.0, min(1.0, -z / 3.0))


def flow_signal(token_id: str, current_price: float) -> float:
    """Near-touch book imbalance → [-1, +1].

    Full-book depth is dominated by far-OTM walls (e.g. asks at 0.999 with
    millions of shares) that say nothing about direction — they pinned the
    old signal at -1.0 for every market under 0.50. Instead compare depth of
    the 5 levels nearest the touch on each side: real pressure lives there.
    """
    book = fetch_order_book(token_id)
    if not book:
        return 0.0
    bids = [(float(b["price"]), float(b["size"])) for b in book.get("bids", [])]
    asks = [(float(a["price"]), float(a["size"])) for a in book.get("asks", [])]
    if not bids or not asks:
        return 0.0
    # Keep only levels within 10 cents of the current price
    near_bids = [(p, s) for p, s in bids if current_price - p <= 0.10]
    near_asks = [(p, s) for p, s in asks if p - current_price <= 0.10]
    if not near_bids and not near_asks:
        return 0.0
    bid_depth = sum(p * s for p, s in near_bids)
    ask_depth = sum(p * s for p, s in near_asks)
    total = bid_depth + ask_depth
    if total == 0:
        return 0.0
    return max(-1.0, min(1.0, (bid_depth - ask_depth) / total * 2.0))


