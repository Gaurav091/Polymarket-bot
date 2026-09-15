"""
Spread analysis — extracted from markets.py.

Fetches and filters bid-ask spreads from the CLOB order book.
Wide spreads indicate low liquidity and hidden execution cost.
"""
from __future__ import annotations

import logging

from . import config
from . import http
from .markets import Market

log = logging.getLogger(__name__)

def fetch_spread(token_id: str) -> float | None:
    """Fetch bid-ask spread for a token.
    
    Returns the spread in dollars (e.g. 0.05 = 5¢).
    Returns None if the book is empty or fetch fails.
    """
    try:
        resp = http.get(
            f"{config.CLOB_HOST}/book",
            params={"token_id": token_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        book = resp.json()
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        if not bids or not asks:
            return None
        best_bid = max(float(b["price"]) for b in bids)
        best_ask = min(float(a["price"]) for a in asks)
        return best_ask - best_bid
    except Exception as e:
        log.debug(f"[markets] spread fetch error: {e}")
        return None


def fetch_batch_spreads(token_ids: list[str]) -> dict[str, float]:
    """Fetch spreads for multiple tokens (one call per token, but batched).
    
    Returns {token_id: spread_dollars}.
    """
    results: dict[str, float] = {}
    for tid in token_ids:
        spread = fetch_spread(tid)
        if spread is not None:
            results[tid] = spread
    return results


def filter_by_spread(markets: list[Market], max_spread: float = config.MAX_SPREAD_USD) -> list[Market]:
    """Filter out markets with spreads wider than max_spread.
    
    Wide spreads indicate:
    - Low liquidity (our fills will be worse than mid)
    - Market maker uncertainty (our edge estimates are less reliable)
    - Hidden cost that eats into our calculated edge
    """
    if not markets:
        return markets
    # Collect all YES token IDs
    token_ids = []
    token_map: dict[str, Market] = {}
    for m in markets:
        tid = m.token_id("YES")
        if tid:
            token_ids.append(tid)
            token_map[tid] = m
    if not token_ids:
        return markets
    # Fetch spreads in batch
    spreads = fetch_batch_spreads(token_ids)
    # Filter
    filtered = []
    for m in markets:
        tid = m.token_id("YES")
        if tid and tid in spreads:
            spread = spreads[tid]
            if spread > max_spread:
                log.debug(f"[markets] rejecting {m.question[:40]} — spread {spread:.3f} > {max_spread}")
                continue
        filtered.append(m)
    if len(filtered) < len(markets):
        log.info(f"[markets] spread filter: {len(markets)} → {len(filtered)} (rejected {len(markets) - len(filtered)} wide-spread)")
    return filtered
