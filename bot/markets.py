"""
Market data — fetches active markets from Polymarket's Gamma API.

IMPORTANT: uses `requests` (never httpx/aiohttp — both hang on this machine).

Enhancements:
- Batch price fetching: single CLOB call for all token IDs
- Spread awareness: reject wide-spread markets where edge gets eaten
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import requests

from . import config
from . import http

log = logging.getLogger(__name__)

# Polymarket CLOB minimums (from Polymarket-bot repo):
# price * size >= $1 and size >= 5 shares
MIN_ORDER_VALUE_USDC = 1.0
MIN_ORDER_SIZE_SHARES = 5.0

# Spread filter: reject markets wider than this (hides hidden cost)
MAX_SPREAD_USD = 0.08  # 8¢ — wider spreads eat our edge


@dataclass
class Market:
    condition_id: str
    question: str
    slug: str
    yes_price: float
    no_price: float
    volume: float
    end_date: str
    tokens: list = field(default_factory=list)

    @property
    def implied_probability(self) -> float:
        return self.yes_price

    def token_id(self, side: str) -> str | None:
        """Get the CLOB token id for a side. Handles Yes/No and custom outcome
        names (e.g. 'Trump'/'Harris'): side 'YES' = first token, 'NO' = second."""
        want = side.upper()
        for t in self.tokens:
            outcome = t.get("outcome", "")
            if outcome.lower() == ("yes" if want == "YES" else "no"):
                return t.get("token_id")
        # Fallback for custom outcome names: YES = token 0, NO = token 1
        # (Polymarket binary markets always list the YES-equivalent first)
        idx = 0 if want == "YES" else 1
        if len(self.tokens) > idx:
            return self.tokens[idx].get("token_id")
        return None


def _parse_json_field(value):
    """Gamma API returns some fields as JSON strings."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return value or []


def _parse_market(m: dict) -> Market | None:
    """Parse a single Gamma API market dict into a Market. Returns None if unusable."""
    try:
        prices = _parse_json_field(m.get("outcomePrices", ""))
        yes_price = float(prices[0]) if len(prices) >= 1 else 0.5
        no_price = float(prices[1]) if len(prices) >= 2 else 1 - yes_price

        clob_token_ids = _parse_json_field(m.get("clobTokenIds", ""))
        outcomes = _parse_json_field(m.get("outcomes", "")) or ["Yes", "No"]
        tokens = [
            {
                "token_id": tid,
                "outcome": outcomes[i] if i < len(outcomes) else f"Outcome_{i}",
                "price": yes_price if i == 0 else no_price,
            }
            for i, tid in enumerate(clob_token_ids)
        ]

        volume = float(m.get("volume", 0) or 0)
        question = m.get("question", "")
        if not question or (yes_price in (0.0, 1.0) and volume == 0):
            return None

        return Market(
            condition_id=m.get("conditionId", m.get("id", "")),
            question=question,
            slug=m.get("slug", ""),
            yes_price=yes_price,
            no_price=no_price,
            volume=volume,
            end_date=m.get("endDate", ""),
            tokens=tokens,
        )
    except (KeyError, ValueError, TypeError, IndexError):
        return None


def _fetch_page(page: int, remaining: int) -> list[dict]:
    """Fetch one page of markets from Gamma API.
    Retries transient failures (Gamma intermittently 404s/resets under load)."""
    last_err = None
    for attempt in range(3):
        try:
            resp = http.get(
                f"{config.GAMMA_API}/markets",
                params={
                    "limit": min(100, remaining),
                    "active": "true",
                    "closed": "false",
                    "order": "volume",
                    "ascending": "false",
                    "offset": page * 100,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            items = data if isinstance(data, list) else data.get("data", [])
            return items
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 * (attempt + 1))  # backoff: 2s, 4s
    log.warning(f"[markets] Gamma API error (page {page}, 3 attempts): {last_err}")
    return []


def fetch_active_markets(limit: int = 100, max_pages: int = 5) -> list[Market]:
    """Fetch active, liquid markets sorted by volume. Paginates (API caps at 100/page)."""
    markets: list[Market] = []
    seen: set[str] = set()
    for page in range(max_pages):
        remaining = limit - len(markets)
        if remaining <= 0:
            break
        items = _fetch_page(page, remaining)
        if not items:
            break
        for m in items:
            parsed = _parse_market(m)
            if parsed is not None and parsed.condition_id not in seen:
                seen.add(parsed.condition_id)
                markets.append(parsed)
        if len(items) < 100:
            break

    markets.sort(key=lambda x: x.volume, reverse=True)
    return markets


def filter_niche(markets: list[Market]) -> list[Market]:
    """PolyAgent's edge: only trade niche markets where the crowd is slow."""
    return [
        m for m in markets
        if config.MIN_VOLUME_USD <= m.volume <= config.MAX_VOLUME_USD
        # Entry-floor: journal data proves the cheap zone bleeds (15-20c =
        # 940% WR, -$104) while 214-354c nets +$14 and >804c nets +$364.
        # Configurable via MIN_ENTRY_PRICE; tuned to sit above the lottery zone.
        and config.MIN_ENTRY_PRICE < m.yes_price < 0.931
    ]


def get_current_price(condition_id: str) -> tuple[float, float] | None:
    """Fetch current (yes, no) prices for a market by condition id."""
    try:
        resp = http.get(
            f"{config.GAMMA_API}/markets",
            params={"condition_ids": condition_id},
        )
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return None
        prices = _parse_json_field(items[0].get("outcomePrices", ""))
        if len(prices) >= 2:
            return float(prices[0]), float(prices[1])
    except Exception as e:
        log.warning(f"[markets] price fetch error: {e}")
    return None


# ============================================================
# Batch price fetching (from polymarket-cli clob prices)
# ============================================================

def fetch_batch_prices(token_ids: list[str]) -> dict[str, tuple[float, float]]:
    """Fetch prices for multiple tokens in a single CLOB call.
    
    The CLOB /prices endpoint supports comma-separated token IDs.
    Returns {token_id: (yes_price, no_price)}.
    
    This is 5-10x faster than fetching one market at a time.
    """
    if not token_ids:
        return {}
    # CLOB /prices accepts comma-separated token IDs
    # Batch in groups of 20 to avoid URL length limits
    results: dict[str, tuple[float, float]] = {}
    batch_size = 20
    for i in range(0, len(token_ids), batch_size):
        batch = token_ids[i:i + batch_size]
        ids_str = ",".join(batch)
        try:
            resp = http.get(
                f"{config.CLOB_HOST}/prices",
                params={"token_ids": ids_str},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            # Response format: {"prices": {"token_id": "price_string", ...}}
            prices_dict = data.get("prices", {})
            for tid, price_str in prices_dict.items():
                try:
                    price = float(price_str)
                    results[tid] = (price, 1.0 - price)
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            log.debug(f"[markets] batch price fetch error: {e}")
    return results


# ============================================================
# Spread analysis (from poly-maker orderbook pattern)
# ============================================================

