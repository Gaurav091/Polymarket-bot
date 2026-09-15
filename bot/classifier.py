"""
Classifier — LLM-based news classification (from PolyAgent's classifier.py).

Asks "does this news make YES more or less likely?" instead of
"what's the probability?" — a task LLMs are actually good at.

Falls back to keyword-only mode when no LLM key is configured.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

from . import config
from .markets import Market

log = logging.getLogger(__name__)

# Circuit breaker: after 3 consecutive LLM failures, stop calling the LLM
# for the rest of the session and use keyword fallback only.
_LLM_FAIL_COUNT = 0
_LLM_DISABLED = False
_LLM_FAIL_LIMIT = 3

CLASSIFICATION_PROMPT = """You are a news classifier for prediction markets.

## Market Question
{question}

## Current Market Price
YES: {yes_price:.2f} (implied probability: {yes_price:.0%})

## Breaking News
{headline}
Source: {source}

## Task
Does this news make the market question MORE likely to resolve YES, MORE likely to resolve NO, or is it NOT RELEVANT?

Also rate the MATERIALITY — how much should this move the price? 0.0 means no impact, 1.0 means this is definitive evidence.

Respond with ONLY valid JSON:
{{
  "direction": "bullish" | "bearish" | "neutral",
  "materiality": <float 0.0 to 1.0>,
  "reasoning": "<1 sentence>"
}}"""


@dataclass
class Classification:
    direction: str  # "bullish", "bearish", "neutral"
    materiality: float  # 0.0-1.0
    reasoning: str
    latency_ms: int
    model: str


# Keyword-based fallback when no LLM is configured — weighted lexicon.
# Each word carries a sentiment weight; headline score = sum of weights.
BULLISH_WORDS = {
    "wins": 2, "won": 2, "beats": 2, "beat": 2, "record": 1, "surge": 2,
    "soars": 2, "rally": 1, "breakthrough": 2, "approves": 2, "approved": 2,
    "passes": 2, "passed": 2, "confirms": 1, "confirmed": 1, "announces": 1,
    "launches": 1, "signs": 1, "achieves": 2, "hits": 1, "deal": 1,
    "agreement": 1, "success": 2, "successful": 2, "wins approval": 3,
    "breaks record": 3, "all-time high": 2, "upbeat": 1, "strong": 1,
}
BEARISH_WORDS = {
    "loses": 2, "lost": 2, "fails": 2, "failed": 2, "misses": 2, "missed": 2,
    "crashes": 2, "plunges": 2, "drops": 1, "falls": 1, "rejects": 2,
    "rejected": 2, "blocks": 2, "blocked": 2, "denies": 2, "denied": 2,
    "delays": 1, "delayed": 1, "cancels": 2, "cancelled": 2, "bans": 2,
    "banned": 2, "sues": 1, "sued": 1, "investigates": 1, "resigns": 2,
    "resignation": 2, "collapse": 2, "crisis": 1, "scandal": 2, "fraud": 3,
    "bankruptcy": 3, "default": 2, "recession": 2, "layoffs": 2,
    "shut down": 2, "shelved": 2, "halted": 1, "weak": 1, "disappointing": 2,
}


def _keyword_classify(headline: str) -> Classification:
    """Weighted-lexicon sentiment. Returns materiality scaled by |score|."""
    words = re.findall(r"[a-z]+", headline.lower())
    bull = sum(BULLISH_WORDS.get(w, 0) for w in words)
    bear = sum(BEARISH_WORDS.get(w, 0) for w in words)
    net = bull - bear
    if net == 0:
        return Classification("neutral", 0.0, "no keyword match", 0, "keyword-lexicon")
    direction = "bullish" if net > 0 else "bearish"
    # Materiality: |net| of 3+ → 0.6+ (tradeable); cap at 1.0
    materiality = min(1.0, abs(net) / 5.0)
    return Classification(direction, materiality, f"lexicon net={net}", 0, "keyword-lexicon")


def _extract_json(text: str) -> dict:
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def classify(headline: str, market: Market, source: str = "unknown") -> Classification:
    """Classify a news headline against a market question."""
    global _LLM_DISABLED, _LLM_FAIL_COUNT

    has_llm_key = any([
        config.ANTHROPIC_API_KEY,
        config.OPENAI_API_KEY,
        config.OPENROUTER_API_KEY,
        config.GEMINI_API_KEY,
        config.XAI_API_KEY,
        config.GROQ_API_KEY,
    ])
    if not has_llm_key or _LLM_DISABLED:
        return _keyword_classify(headline)

    start = time.time()
    prompt = CLASSIFICATION_PROMPT.format(
        question=market.question,
        yes_price=market.yes_price,
        headline=headline,
        source=source,
    )

    try:
        from litellm import completion

        response = completion(
            model=config.CLASSIFICATION_MODEL,
            max_tokens=2000,  # thinking models burn budget on reasoning — 200 truncates JSON
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content.strip()
        result = _extract_json(text)
        latency = int((time.time() - start) * 1000)

        direction = result.get("direction", "neutral")
        if direction not in ("bullish", "bearish", "neutral"):
            direction = "neutral"
        materiality = max(0.0, min(1.0, float(result.get("materiality", 0))))

        return Classification(
            direction=direction,
            materiality=materiality,
            reasoning=result.get("reasoning", ""),
            latency_ms=latency,
            model=config.CLASSIFICATION_MODEL,
        )
    except Exception as e:
        _LLM_FAIL_COUNT += 1
        if _LLM_FAIL_COUNT >= _LLM_FAIL_LIMIT:
            _LLM_DISABLED = True
            log.warning(
                f"[classifier] LLM failed {_LLM_FAIL_COUNT}x — disabling LLM for this "
                f"session, keyword fallback only ({type(e).__name__})"
            )
        else:
            log.warning(f"[classifier] LLM error: {e} — falling back to keywords")
        return _keyword_classify(headline)
