"""
Macro data layer — free external signals for regime detection.

Pulls from:
1. FRED (economic indicators: Fed Funds Rate, CPI, unemployment)
2. CoinGecko (BTC/ETH/SOL prices + 24h change)
3. Yahoo Finance (VIX, S&P 500, Gold)
4. DeFi Llama (total DeFi TVL trend)

Each returns a score in [-1, +1] or raw values cached for 15 min.
Used by the quant ensemble and edge detection for regime-aware sizing.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

from . import config
from .macro_data import (
    fetch_fed_rate, fetch_cpi, fetch_unemployment,
    fetch_crypto_prices, fetch_vix, fetch_sp500, fetch_gold,
    fetch_defi_tvl, crypto_regime_score, vix_regime_score,
    defi_regime_score, _newsapi_fetch_keyword,
    fetch_newsapi_headlines, _yahoo_quote,
)

log = logging.getLogger(__name__)

# ============================================================
# Cache (shared across all macro sources)
# ============================================================

@dataclass
class _CacheEntry:
    data: Any
    ts: float

_cache: dict[str, _CacheEntry] = {}
_DEFAULT_TTL = 900.0  # 15 min


def _cached(key: str, fetcher, ttl: float = _DEFAULT_TTL) -> Any:
    entry = _cache.get(key)
    if entry and time.time() - entry.ts < ttl:
        return entry.data
    try:
        result = fetcher()
        _cache[key] = _CacheEntry(data=result, ts=time.time())
        return result
    except Exception as exc:
        log.debug("[macro] %s fetch failed: %s", key, exc)
        return None


# ============================================================
# 1. FRED — Federal Reserve Economic Data
# ============================================================

# ============================================================
# 2. CoinGecko — crypto prices (no API key)
# ============================================================

# ============================================================
# 3. Yahoo Finance — VIX, S&P 500, Gold (no API key)
# ============================================================

# ============================================================
# 4. DeFi Llama — on-chain TVL trend
# ============================================================

# ============================================================
# 5. NewsAPI.ai (Event Registry) — targeted news
# ============================================================

def fetch_newsapi_headlines(query: str = "prediction market",
                            page_size: int = 3) -> list[dict]:
    """Fetch recent headlines from newsapi.ai (Event Registry, free tier: 2000 tokens/month).

    Each keyword search costs 1 token. With 1 keyword and 1-hour cache,
    this uses ~24 tokens/day (~720/month = 36% of free tier).
    """
    key = config.NEWS_API_KEY
    if not key:
        return []

    keywords = [kw.strip() for kw in query.split(",") if kw.strip()] or ["bitcoin"]

    def _fetch_all():
        seen: set[str] = set()
        out: list[dict] = []
        for kw in keywords[:3]:
            try:
                for article in _newsapi_fetch_keyword(kw, key, page_size):
                    if article["title"] not in seen:
                        seen.add(article["title"])
                        out.append(article)
            except Exception as exc:
                log.debug("[macro] newsapi.ai fetch '%s' failed: %s", kw, exc)
        return out

    return _cached("newsapi:ai:all", _fetch_all, ttl=3600.0) or []  # 1h cache — free tier is 2000 tokens/month


# ============================================================
# Aggregate macro context
# ============================================================

@dataclass
class MacroContext:
    """Snapshot of external macro conditions."""
    fed_rate: float | None = None
    cpi: float | None = None
    unemployment: float | None = None
    btc_usd: float | None = None
    btc_24h_change: float | None = None
    eth_usd: float | None = None
    vix: float | None = None
    sp500: float | None = None
    gold: float | None = None
    defi_tvl_b: float | None = None
    regime_score: float = 0.0  # aggregate [-1, +1]

    def summary(self) -> str:
        parts = []
        if self.fed_rate is not None:
            parts.append(f"FedRate={self.fed_rate:.2f}%")
        if self.vix is not None:
            parts.append(f"VIX={self.vix:.1f}")
        if self.sp500 is not None:
            parts.append(f"SPX={self.sp500:.0f}")
        if self.btc_usd is not None:
            parts.append(f"BTC=${self.btc_usd:,.0f}")
        if self.gold is not None:
            parts.append(f"Gold=${self.gold:.0f}")
        parts.append(f"regime={self.regime_score:+.2f}")
        return " | ".join(parts)


def fetch_macro_context() -> MacroContext:
    """Fetch all macro data in parallel-safe sequential calls.

    Each source is independently cached (15 min TTL), so repeated calls
    within the window are free. This function is called once per scan cycle.
    """
    ctx = MacroContext()

    # FRED
    ctx.fed_rate = fetch_fed_rate()
    ctx.cpi = fetch_cpi()
    ctx.unemployment = fetch_unemployment()

    # CoinGecko
    prices = fetch_crypto_prices()
    btc = prices.get("bitcoin", {})
    ctx.btc_usd = btc.get("usd")
    ctx.btc_24h_change = btc.get("usd_24h_change")
    ctx.eth_usd = prices.get("ethereum", {}).get("usd")

    # Yahoo Finance
    ctx.vix = fetch_vix()
    ctx.sp500 = fetch_sp500()
    ctx.gold = fetch_gold()

    # DeFi Llama
    tvl = fetch_defi_tvl()
    if tvl:
        ctx.defi_tvl_b = tvl["current"] / 1e9

    # Aggregate regime score (weighted average of sub-scores)
    scores = []
    weights = []
    cr = crypto_regime_score()
    if abs(cr) > 1e-9:
        scores.append(cr)
        weights.append(0.3)  # crypto is most relevant for Polymarket
    vr = vix_regime_score()
    if abs(vr) > 1e-9:
        scores.append(vr)
        weights.append(0.3)
    dr = defi_regime_score()
    if abs(dr) > 1e-9:
        scores.append(dr)
        weights.append(0.2)

    # SP500 direction
    sp = _yahoo_quote("^GSPC")
    if sp and sp["prev_close"] and sp["price"]:
        sp_change = (sp["price"] - sp["prev_close"]) / sp["prev_close"]
        scores.append(max(-1.0, min(1.0, sp_change * 50)))
        weights.append(0.2)

    if weights:
        total_w = sum(weights)
        ctx.regime_score = sum(s * w for s, w in zip(scores, weights)) / total_w

    log.info("[macro] %s", ctx.summary())
    return ctx
