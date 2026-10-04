"""
News stream — polls RSS feeds for breaking headlines.

Uses `requests` (never httpx/aiohttp — both hang on this machine).
Deduplicates headlines so each is processed exactly once.
"""
from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

import requests

from . import http

from . import config

log = logging.getLogger(__name__)

UA = {"User-Agent": "Mozilla/5.0 (compatible; polymarket-survival-bot/1.0)"}

# Similarity threshold for fuzzy deduplication (0.0-1.0)
# 0.85 = quite similar, likely same story
NEWS_SIMILARITY_THRESHOLD = 0.85


@dataclass
class NewsEvent:
    headline: str
    source: str
    url: str
    received_at: datetime
    summary: str = ""

    def age_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.received_at).total_seconds()


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _normalize_headline(text: str) -> str:
    """Normalize headline for comparison: lowercase, remove punctuation, extra spaces."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _is_similar(h1: str, h2: str, threshold: float = NEWS_SIMILARITY_THRESHOLD) -> bool:
    """Check if two headlines are similar using fuzzy matching."""
    # Cheap length gate: ratio = 2*min/(sum), so similarity >= threshold is
    # impossible when the lengths differ by more than 1/threshold. Skipping
    # here turns the O(n^2) dedup from ~320s into a few seconds — without it
    # the poll blocked the main trading loop for 5+ minutes per cycle.
    if not h1 or not h2:
        return False
    lo, hi = (len(h1), len(h2)) if len(h1) <= len(h2) else (len(h2), len(h1))
    if hi > lo / threshold:
        return False
    return SequenceMatcher(None, h1, h2).ratio() >= threshold


def _parse_feed(xml_text: str, source: str) -> list[NewsEvent]:
    """Parse an RSS/Atom feed into NewsEvents."""
    events: list[NewsEvent] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return events

    # RSS 2.0
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = _strip_html(item.findtext("description") or "")[:300]
        if title:
            events.append(
                NewsEvent(
                    headline=title,
                    source=source,
                    url=link,
                    received_at=datetime.now(timezone.utc),
                    summary=desc,
                )
            )

    # Atom
    ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.iter(f"{ns}entry"):
        title = (entry.findtext(f"{ns}title") or "").strip()
        link_el = entry.find(f"{ns}link")
        link = link_el.get("href", "") if link_el is not None else ""
        if title:
            events.append(
                NewsEvent(
                    headline=title,
                    source=source,
                    url=link,
                    received_at=datetime.now(timezone.utc),
                )
            )
    return events


class NewsPoller:
    """Polls RSS feeds on an interval, yielding only new headlines."""

    # Blocking index: only headlines sharing at least one content token are
    # fuzzy-compared. Cap keeps pathological cases (one token in thousands of
    # headlines) bounded.
    _MAX_CANDIDATES = 60
    _STOPWORDS = frozenset(
        "the a an and or but of to in on for with at by from as is are was "
        "were be been it its this that these those he she they we you i "
        "not no yes will would can could may might must new says said after "
        "before over under about into out up down more most".split()
    )

    def __init__(self):
        self._seen: set[str] = set()  # exact match keys
        self._seen_normalized: list[str] = []  # for fuzzy matching
        self._token_index: dict[str, list[int]] = {}  # token -> positions
        self._last_poll = 0.0

    def _remember(self, norm: str) -> None:
        """Index a normalized headline for later candidate lookup."""
        pos = len(self._seen_normalized)
        self._seen_normalized.append(norm)
        for tok in set(norm.split()):
            if len(tok) < 4 or tok in self._STOPWORDS:
                continue
            bucket = self._token_index.setdefault(tok, [])
            bucket.append(pos)
            if len(bucket) > 500:
                del bucket[:-250]  # bound index growth on hot tokens

    def _is_new(self, key: str, norm: str) -> bool:
        """True when this headline differs from everything seen so far."""
        if key in self._seen:
            return False
        if not self._seen_normalized:
            self._remember(norm)
            return True
        # Candidate retrieval: headlines sharing a content token.
        cand: set[int] = set()
        for tok in set(norm.split()):
            if len(tok) < 4 or tok in self._STOPWORDS:
                continue
            for pos in self._token_index.get(tok, ()):
                cand.add(pos)
                if len(cand) >= self._MAX_CANDIDATES:
                    break
            if len(cand) >= self._MAX_CANDIDATES:
                break
        # No shared token → cannot be a near-duplicate (different story).
        if not cand:
            self._remember(norm)
            return True
        for pos in cand:
            if _is_similar(norm, self._seen_normalized[pos]):
                return False
        self._remember(norm)
        return True

    def _poll_newsapi(self) -> list[NewsEvent]:
        """Fetch headlines from newsapi.ai (Event Registry, free tier: 2000 tokens/month)."""
        if not config.NEWS_API_KEY:
            return []
        from .macro import fetch_newsapi_headlines
        events: list[NewsEvent] = []
        for article in fetch_newsapi_headlines(page_size=5):
            title = (article.get("title") or "").strip()
            if not title or title == "[Removed]":
                continue
            key = title.lower()[:200]
            norm = _normalize_headline(title)
            if self._is_new(key, norm):
                self._seen.add(key)
                events.append(NewsEvent(
                    headline=title,
                    source="newsapi.ai",
                    url=article.get("url", ""),
                    received_at=datetime.now(timezone.utc),
                    summary=(article.get("description") or "")[:300],
                ))
        return events

    def poll(self) -> list[NewsEvent]:
        """Fetch all feeds, return only headlines not seen before."""
        if time.time() - self._last_poll < config.NEWS_POLL_SECONDS:
            return []
        self._last_poll = time.time()

        fresh: list[NewsEvent] = []
        for feed_url in config.RSS_FEEDS:
            try:
                resp = http.get(feed_url, headers=UA)  # hard-capped in watchdog
                resp.raise_for_status()
                for event in _parse_feed(resp.text, source=feed_url.split("/")[2]):
                    key = event.headline.lower()[:200]
                    norm = _normalize_headline(event.headline)
                    if self._is_new(key, norm):
                        self._seen.add(key)
                        fresh.append(event)
            except Exception as e:
                log.debug(f"[news] feed error {feed_url}: {e}")

        # NewsAPI headlines (separate source, cached in macro.py)
        try:
            fresh.extend(self._poll_newsapi())
        except Exception as e:
            log.debug("[news] NewsAPI error: %s", e)

        # Cap memory: keep only last 5000 seen keys
        if len(self._seen) > 5000:
            self._seen = set(list(self._seen)[-2500:])
            self._seen_normalized = self._seen_normalized[-2500:]
            self._token_index = {}
            for i, norm in enumerate(self._seen_normalized):
                for tok in set(norm.split()):
                    if len(tok) < 4 or tok in self._STOPWORDS:
                        continue
                    self._token_index.setdefault(tok, []).append(i)
        return fresh
