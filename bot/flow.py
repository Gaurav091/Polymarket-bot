"""
On-chain trade flow signal — detects whale activity and smart money.

Uses Polymarket's free Gamma API and CLOB endpoints to detect:
1. Recent trade flow (who's buying/selling)
2. Whale activity (large fills)
3. Maker/taker ratio (informed vs noise flow)
4. Trade velocity (unusual activity)

This fires BEFORE news hits public feeds — the leading signal.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from . import http
from .markets import Market

log = logging.getLogger(__name__)

CLOB_HOST = "https://clob.polymarket.com"
DATA_API_HOST = "https://data-api.polymarket.com"

# Whale threshold: trades larger than this are "smart money" signals
WHALE_USD_THRESHOLD = 500.0

# Only count fills this recent as "current flow". Without a window, a market
# that traded heavily months ago looks like it has live whale activity. With a
# window too short, niche markets return 0-2 fills and confidence collapses to
# 0 — 6h balances staleness against coverage.
FLOW_WINDOW_SECONDS = 21600.0

# Flow signal weight in the ensemble
FLOW_WEIGHT = 0.15


@dataclass
class FlowSignal:
    """Aggregated flow analysis for a market."""
    net_direction: float     # -1 to +1: positive = more buying
    whale_bias: float        # -1 to +1: whale direction
    trade_count: int         # recent trade count
    avg_trade_size: float    # average trade size in USD
    confidence: float        # 0 to 1: how reliable is this signal


def _fetch_recent_trades(market: Market, limit: int = 200) -> list[dict]:
    """Fetch recent fills for a market, normalized to the YES perspective.

    CLOB `/trades` is authenticated (401) and has been dead since ~2026-09.
    The public `data-api` `/trades` endpoint takes the condition id — not the
    token id — and returns both outcome tokens, so a trade is re-expressed as
    BUY/SELL *of YES* before it reaches `_analyze_flow`.
    """
    condition_id = market.condition_id
    if not condition_id:
        return []
    try:
        resp = http.get(
            f"{DATA_API_HOST}/trades",
            params={"market": condition_id, "limit": limit},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        rows = data if isinstance(data, list) else data.get("data", [])
    except Exception as e:
        log.debug(f"[flow] trades fetch failed: {e}")
        return []

    yes_token = market.token_id("YES")
    no_token = market.token_id("NO")
    now = time.time()
    normalized: list[dict] = []
    for trade in rows:
        # Stale fills say nothing about current order flow.
        try:
            if now - float(trade.get("timestamp", 0)) > FLOW_WINDOW_SECONDS:
                continue
        except (TypeError, ValueError):
            continue
        side = str(trade.get("side", "")).upper()
        asset = trade.get("asset")
        if asset == no_token and side in ("BUY", "SELL"):
            side = "SELL" if side == "BUY" else "BUY"
        elif yes_token and asset != yes_token and asset != no_token:
            # Unknown outcome token — don't guess its direction.
            continue
        normalized.append({**trade, "side": side})
    return normalized


def _fetch_order_book_depth(token_id: str) -> dict | None:
    """Fetch order book for spread and depth analysis."""
    try:
        resp = http.get(
            f"{CLOB_HOST}/book",
            params={"token_id": token_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.debug(f"[flow] book fetch failed: {e}")
        return None


def _analyze_flow(trades: list[dict]) -> tuple[float, float, int, float]:
    """Analyze trade flow direction and whale activity.
    
    Returns: (net_direction, whale_bias, trade_count, avg_size)
    """
    if not trades:
        return 0.0, 0.0, 0, 0.0

    buy_volume = 0.0
    sell_volume = 0.0
    whale_buys = 0.0
    whale_sells = 0.0
    total_size = 0.0

    for trade in trades:
        # Trade structure from CLOB API: {side, price, size, ...}
        side = trade.get("side", "").upper()
        price = float(trade.get("price", 0))
        size = float(trade.get("size", 0))
        usd_value = price * size

        total_size += usd_value

        if side == "BUY":
            buy_volume += usd_value
            if usd_value >= WHALE_USD_THRESHOLD:
                whale_buys += usd_value
        else:
            sell_volume += usd_value
            if usd_value >= WHALE_USD_THRESHOLD:
                whale_sells += usd_value

    total = buy_volume + sell_volume
    if total == 0:
        return 0.0, 0.0, len(trades), 0.0

    # Net direction: positive = more buying pressure
    net_dir = (buy_volume - sell_volume) / total

    # Whale bias
    whale_total = whale_buys + whale_sells
    if whale_total > 0:
        whale_bias = (whale_buys - whale_sells) / whale_total
    else:
        whale_bias = 0.0

    avg_size = total_size / len(trades) if trades else 0.0

    return net_dir, whale_bias, len(trades), avg_size


def _compute_spread(book: dict | None) -> float | None:
    """Compute bid-ask spread from order book."""
    if not book:
        return None
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    if not bids or not asks:
        return None
    best_bid = max(float(b["price"]) for b in bids)
    best_ask = min(float(a["price"]) for a in asks)
    return best_ask - best_bid


def compute_flow_signal(market: Market) -> FlowSignal:
    """Compute on-chain flow signal for a market.
    
    Returns a FlowSignal with direction, whale bias, and confidence.
    """
    token_id = market.token_id("YES")
    if not token_id:
        return FlowSignal(0.0, 0.0, 0, 0.0, 0.0)

    # Fetch recent trades (public data-api, YES-normalized)
    trades = _fetch_recent_trades(market, limit=200)
    net_dir, whale_bias, trade_count, avg_size = _analyze_flow(trades)

    # Fetch book for spread analysis
    book = _fetch_order_book_depth(token_id)
    spread = _compute_spread(book)

    # Confidence: based on trade count and spread
    # More trades = more reliable signal
    # Tighter spread = more liquid = more reliable
    trade_conf = min(1.0, trade_count / 20.0)
    if spread is None:
        spread_conf = 0.2
    elif spread < 0.05:
        spread_conf = 1.0
    elif spread < 0.10:
        spread_conf = 0.5
    else:
        spread_conf = 0.2
    confidence = trade_conf * spread_conf

    # Whale signal gets extra weight (smart money)
    combined_direction = 0.7 * net_dir + 0.3 * whale_bias

    return FlowSignal(
        net_direction=max(-1.0, min(1.0, combined_direction)),
        whale_bias=max(-1.0, min(1.0, whale_bias)),
        trade_count=trade_count,
        avg_trade_size=avg_size,
        confidence=confidence,
    )
