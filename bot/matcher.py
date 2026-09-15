"""
News-to-market matching — keyword overlap scoring (from PolyAgent's matcher.py).
Fast, no API call needed.
"""
from __future__ import annotations

from .markets import Market

STOPWORDS = {
    "will", "the", "a", "an", "be", "by", "in", "on", "at", "to",
    "of", "for", "is", "it", "this", "that", "and", "or", "not",
    "before", "after", "end", "yes", "no", "any", "has", "have",
    "does", "do", "than", "more", "less", "over", "under", "above",
    "below", "through", "during", "between", "reach", "exceed",
}


PUNCT = "?.,!\"'()[]"


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
    """Find markets relevant to a headline via keyword overlap."""
    headline_lower = f"{headline}".lower()
    scored = []

    for market in markets:
        keywords = extract_keywords(market.question)
        if not keywords:
            continue
        hits = sum(1 for kw in keywords if kw in headline_lower)
        if hits == 0:
            continue
        score = hits / len(keywords)
        scored.append((score, market))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:max_matches]]
