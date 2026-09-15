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

import requests

from . import http

from . import config

log = logging.getLogger(__name__)

UA = {"User-Agent": "Mozilla/5.0 (compatible; polymarket-survival-bot/1.0)"}


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

    def __init__(self):
        self._seen: set[str] = set()
        self._last_poll = 0.0

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
            if key not in self._seen:
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
                    if key not in self._seen:
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
        return fresh
