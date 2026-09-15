"""Macro data fetchers — extracted from macro.py."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

from . import config

log = logging.getLogger(__name__)


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

def _fred_observations(series_id: str, limit: int = 5) -> list[dict]:
    key = config.FRED_API_KEY
    if not key:
        return []
    r = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={"series_id": series_id, "api_key": key,
                "file_type": "json", "sort_order": "desc", "limit": limit},
        timeout=10, verify=False,
    )
    r.raise_for_status()
    return r.json().get("observations", [])


def fetch_fed_rate() -> float | None:
    """Current Fed Funds Effective Rate (DFF)."""
    obs = _cached("fred:dff", lambda: _fred_observations("DFF", 3))
    if not obs:
        return None
    for o in obs:
        val = o.get("value")
        if val and val != ".":
            return float(val)
    return None


def fetch_cpi() -> float | None:
    """Latest CPI (CPIAUCSL) — headline inflation."""
    obs = _cached("fred:cpi", lambda: _fred_observations("CPIAUCSL", 3))
    if not obs:
        return None
    for o in obs:
        val = o.get("value")
        if val and val != ".":
            return float(val)
    return None


def fetch_unemployment() -> float | None:
    """Latest unemployment rate (UNRATE)."""
    obs = _cached("fred:unrate", lambda: _fred_observations("UNRATE", 3))
    if not obs:
        return None
    for o in obs:
        val = o.get("value")
        if val and val != ".":
            return float(val)
    return None


def fetch_crypto_prices() -> dict[str, dict]:
    """BTC, ETH, SOL prices + 24h change."""
    def _fetch():
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin,ethereum,solana",
                    "vs_currencies": "usd",
                    "include_24hr_change": "true"},
            timeout=10, verify=False,
        )
        r.raise_for_status()
        return r.json()
    return _cached("coingecko:prices", _fetch) or {}


def crypto_regime_score() -> float:
    """[-1, +1] from BTC 24h change. Negative = risk-off, positive = risk-on."""
    prices = fetch_crypto_prices()
    btc = prices.get("bitcoin", {})
    change = btc.get("usd_24h_change", 0.0)
    # Map ±10% change to ±1.0
    return max(-1.0, min(1.0, change / 10.0))


def _yahoo_quote(symbol: str) -> dict | None:
    """Fetch latest quote from Yahoo Finance chart API."""
    def _fetch():
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"interval": "1d", "range": "2d"},
            timeout=10, verify=False,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        r.raise_for_status()
        result = r.json()["chart"]["result"][0]
        meta = result["meta"]
        return {
            "price": meta.get("regularMarketPrice"),
            "prev_close": meta.get("chartPreviousClose"),
        }
    return _cached(f"yahoo:{symbol}", _fetch)


def fetch_vix() -> float | None:
    """CBOE Volatility Index — fear gauge."""
    q = _yahoo_quote("^VIX")
    return q["price"] if q else None


def fetch_sp500() -> float | None:
    """S&P 500 index level."""
    q = _yahoo_quote("^GSPC")
    return q["price"] if q else None


def fetch_gold() -> float | None:
    """Gold futures price."""
    q = _yahoo_quote("GC=F")
    return q["price"] if q else None


def vix_regime_score() -> float:
    """[-1, +1] from VIX level. High VIX = fear = negative for risk assets.

    VIX < 15 → +0.5 (calm, risk-on)
    VIX 15-20 → 0.0 (neutral)
    VIX 20-30 → -0.5 (elevated fear)
    VIX > 30 → -1.0 (panic)
    """
    vix = fetch_vix()
    if vix is None:
        return 0.0
    if vix < 15:
        return 0.5
    if vix < 20:
        return 0.0
    if vix < 30:
        return -0.5
    return -1.0


def fetch_defi_tvl() -> dict | None:
    """Total DeFi TVL in USD."""
    def _fetch():
        r = requests.get(
            "https://api.llama.fi/v2/historicalChainTvl",
            timeout=10, verify=False,
        )
        r.raise_for_status()
        data = r.json()
        if len(data) >= 2:
            latest = data[-1]["tvl"]
            prev = data[-2]["tvl"]
            return {"current": latest, "prev": prev, "change_pct": (latest - prev) / prev * 100}
        return None
    return _cached("llama:tvl", _fetch)


def defi_regime_score() -> float:
    """[-1, +1] from TVL 24h change. Growing TVL = risk-on."""
    tvl = fetch_defi_tvl()
    if not tvl:
        return 0.0
    change = tvl.get("change_pct", 0.0)
    return max(-1.0, min(1.0, change / 3.0))  # ±3% TVL change = ±1.0


def _newsapi_fetch_keyword(kw: str, key: str, page_size: int) -> list[dict]:
    """Fetch articles for one keyword from newsapi.ai. Returns normalized dicts."""
    r = requests.get(
        "https://eventregistry.org/api/v1/article/getArticles",
        params={
            "keyword": kw, "resultType": "articles",
            "articlesSortBy": "date", "articlesCount": page_size,
            "lang": "eng", "apiKey": key,
        },
        timeout=12, verify=False,
    )
    r.raise_for_status()
    raw = r.json().get("articles", {}).get("results", [])
    out: list[dict] = []
    for a in raw:
        title = (a.get("title") or "").strip()
        if not title:
            continue
        src = a.get("source", {})
        out.append({
            "title": title, "url": a.get("url", ""),
            "description": (a.get("body") or "")[:300],
            "source": {"name": src.get("title", "")},
            "publishedAt": a.get("dateTime", ""),
        })
    return out


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

    return _cached("newsapi:ai:all", _fetch_all, ttl=3600.0) or []


