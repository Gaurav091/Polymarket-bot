"""
Kalshi cross-platform arbitrage detector.

Checks if the same event is priced differently on Polymarket vs Kalshi.
If Polymarket YES + Kalshi NO < 1.0 (or vice versa), there's a guaranteed
profit by buying both sides across platforms.

Kalshi API is free for market data (no auth needed for GET /markets).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

from . import http

log = logging.getLogger(__name__)

KALSHI_HOST = "https://api.elections.kalshi.com/trade-api/v2"

# Cache
_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 300.0  # 5 min


@dataclass
class ArbOpportunity:
    """Cross-platform arbitrage between Polymarket and Kalshi."""
    polymarket_question: str
    kalshi_ticker: str
    polymarket_yes_price: float
    kalshi_yes_price: float
    guaranteed_profit_cents: float  # per share
    direction: str  # "poly_yes_kalshi_no" or "poly_no_kalshi_yes"


def _fetch_kalshi_markets(limit: int = 100) -> list[dict]:
    """Fetch active Kalshi markets (free, no auth needed)."""
    now = time.time()
    if "markets" in _cache and now - _cache["markets"][0] < _CACHE_TTL:
        return _cache["markets"][1]

    try:
        resp = http.get(
            f"{KALSHI_HOST}/markets",
            params={"limit": limit, "status": "open"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        markets = data.get("markets", [])
        _cache["markets"] = (now, markets)
        return markets
    except Exception as e:
        log.debug("[kalshi] market fetch failed: %s", e)
        return []


def _normalize_question(text: str) -> str:
    """Normalize market question for fuzzy matching."""
    import re
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _match_kalshi_market(
    poly_normalized: str,
    kalshi_by_title: dict[str, dict],
) -> dict | None:
    """Find matching Kalshi market by normalized question (exact or substring)."""
    for kq, km in kalshi_by_title.items():
        if poly_normalized == kq or poly_normalized in kq or kq in poly_normalized:
            return km
    return None


def _extract_kalshi_price(market: dict) -> float | None:
    """Extract YES price from Kalshi market (uses cents → dollars)."""
    for field in ("yes_ask", "last_price"):
        val = market.get(field)
        if val:
            price = float(val) / 100.0
            if price > 0:
                return price
    return None


def _check_direction(
    pm, kalshi_yes: float, direction: str, min_profit_cents: float,
) -> ArbOpportunity | None:
    """Check one arb direction. Returns ArbOpportunity if profitable."""
    poly_yes = pm.yes_price
    if direction == "poly_yes_kalshi_no":
        cost = poly_yes + (1.0 - kalshi_yes)
    else:
        cost = (1.0 - poly_yes) + kalshi_yes

    profit = 1.0 - cost
    if profit < min_profit_cents:
        return None

    return ArbOpportunity(
        polymarket_question=pm.question,
        kalshi_ticker="",  # filled by caller
        polymarket_yes_price=poly_yes,
        kalshi_yes_price=kalshi_yes,
        guaranteed_profit_cents=round(profit * 100, 1),
        direction=direction,
    )


def find_arb_opportunities(
    poly_markets: list,
    min_profit_cents: float = 0.02,
) -> list[ArbOpportunity]:
    """Check for cross-platform arbitrage between Polymarket and Kalshi.

    Returns opportunities where buying YES on one platform and NO on the
    other guarantees a profit (after fees).
    """
    kalshi_markets = _fetch_kalshi_markets(limit=200)
    if not kalshi_markets:
        return []

    kalshi_by_title: dict[str, dict] = {}
    for km in kalshi_markets:
        title = km.get("title", "") or km.get("subtitle", "")
        if title:
            kalshi_by_title[_normalize_question(title)] = km

    opportunities: list[ArbOpportunity] = []

    for pm in poly_markets:
        matched = _match_kalshi_market(_normalize_question(pm.question), kalshi_by_title)
        if not matched:
            continue

        kalshi_yes = _extract_kalshi_price(matched)
        if kalshi_yes is None:
            continue

        ticker = matched.get("ticker", "")
        for direction in ("poly_yes_kalshi_no", "poly_no_kalshi_yes"):
            opp = _check_direction(pm, kalshi_yes, direction, min_profit_cents)
            if opp:
                opp.kalshi_ticker = ticker
                opps_str = f"{opp.guaranteed_profit_cents:.1f}c"
                log.info("[arb] %s guaranteed — %s", opps_str, pm.question[:50])
                opportunities.append(opp)

    return opportunities
