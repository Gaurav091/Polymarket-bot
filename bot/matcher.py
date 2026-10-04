"""
News-to-market matching — keyword overlap scoring (from PolyAgent's matcher.py).
Fast, no API call needed.
"""
from __future__ import annotations

import re

from .markets import Market

STOPWORDS = {
    "will", "the", "a", "an", "be", "by", "in", "on", "at", "to",
    "of", "for", "is", "it", "this", "that", "and", "or", "not",
    "before", "after", "end", "yes", "no", "any", "has", "have",
    "does", "do", "than", "more", "less", "over", "under", "above",
    "below", "through", "during", "between", "reach", "exceed",
}


PUNCT = "?.,!\"'()[]"

WORD_RE = re.compile(r"[a-z0-9]+")

# Words too generic to justify a match on their own: every sports headline
# contains "win"/"best", and nearly every market question contains a year.
# Previously these alone matched a soccer headline to an England market.
GENERIC = {
    "win", "won", "lose", "lost", "beat", "beats", "best", "top", "new",
    "next", "first", "last", "day", "week", "year", "game", "team",
    "2025", "2026", "2027", "2028", "2029", "2030",
}


def extract_keywords(question: str) -> list[str]:
    words = question.lower().split()
    return [
        w.strip(PUNCT)
        for w in words
        if w.strip(PUNCT) not in STOPWORDS and len(w.strip(PUNCT)) > 2
    ]


def match_news_to_markets(
    headline: str,
    markets: list[Market],
    max_matches: int = 5,
) -> list[Market]:
    """Find markets relevant to a headline via keyword overlap.

    A market only matches when at least one *distinctive* keyword (not in
    GENERIC, >= 4 chars) appears as a whole word in the headline. Generic
    overlap alone produced ~3000 false pairs per news poll, which then fed
    the classifier and opened trades on unrelated markets.
    """
    headline_words = set(WORD_RE.findall(headline.lower()))
    scored = []

    for market in markets:
        keywords = extract_keywords(market.question)
        if not keywords:
            continue
        hits = [kw for kw in keywords if kw in headline_words]
        if not hits:
            continue
        strong = [kw for kw in hits if kw not in GENERIC and len(kw) >= 4]
        if not strong:
            continue
        score = len(strong) * 2 + len(hits)
        scored.append((score, market))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:max_matches]]
