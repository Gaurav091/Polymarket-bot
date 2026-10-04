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

# Circuit breaker: after 3 consecutive LLM failures, pause the LLM for a
# cooldown instead of killing it for the whole session. Free-tier providers
# (OpenRouter :free models) rate-limit transiently — a permanent disable meant
# one 429 burst left the bot on keyword-only mode for days, which caps
# materiality at 0.6 and keeps signals below the trade threshold.
_LLM_FAIL_COUNT = 0
_LLM_DISABLED = False
_LLM_FAIL_LIMIT = 3
_LLM_COOLDOWN_SECONDS = 300.0
_LLM_DISABLED_UNTIL = 0.0

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
    "wins": 2, "won": 2, "beats": 2, "beat": 2, "record": 1, "surge": 2, "surges": 2,
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
    # Materiality: require |net| of 4+ for tradeable signal (was 3+)
    # This reduces false signals from weak keyword matches.
    materiality = min(1.0, abs(net) / 7.0)
    # Keyword-only mode is unreliable — cap materiality at 0.6
    # to prevent overconfident trades from weak signals.
    materiality = min(0.6, materiality)
    return Classification(direction, materiality, f"lexicon net={net}", 0, "keyword-lexicon")


def _safe_load_dict(candidate: str) -> dict | None:
    """Safely parse a JSON string into a dictionary if valid."""
    try:
        val = json.loads(candidate)
        return val if isinstance(val, dict) else None
    except Exception:
        return None


def _extract_from_code_blocks(text: str) -> dict | None:
    """Parse JSON from markdown ``` code blocks."""
    if "```" not in text:
        return None
    for part in text.split("```"):
        trimmed = part.strip()
        if trimmed.startswith("json"):
            trimmed = trimmed[4:].strip()
        parsed = _safe_load_dict(trimmed)
        if parsed is not None:
            return parsed
    return None


def _find_balanced_json_chunks(text: str) -> list[str]:
    """Collect balanced brace substring candidates from text."""
    chunks: list[str] = []
    depth = 0
    start = -1
    for idx, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start != -1:
                chunks.append(text[start : idx + 1])
    return chunks


def _extract_from_braces(text: str) -> dict | None:
    """Try parsing outer braces or balanced JSON object chunks."""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        parsed = _safe_load_dict(text[start : end + 1])
        if parsed is not None:
            return parsed
    for chunk in _find_balanced_json_chunks(text):
        parsed = _safe_load_dict(chunk)
        if parsed and "direction" in parsed:
            return parsed
    return None


def _extract_json(text: str) -> dict:
    """Extract JSON object from LLM response text."""
    extracted = _extract_from_code_blocks(text) or _extract_from_braces(text)
    if extracted is not None:
        return extracted
    return json.loads(text)


def _response_text(response) -> str:
    """Pull text out of a litellm response.

    Thinking models often return `content=None` with everything in
    `reasoning_content` (or vice versa) once `max_tokens` is hit — calling
    `.strip()` on None crashed classify() and silently degraded to keywords.
    """
    msg = response.choices[0].message
    for attr in ("content", "reasoning_content"):
        text = getattr(msg, attr, None)
        if text and text.strip():
            return text.strip()
    return ""


def classify(headline: str, market: Market, source: str = "unknown") -> Classification:
    """Classify a news headline against a market question."""
    global _LLM_DISABLED, _LLM_FAIL_COUNT, _LLM_DISABLED_UNTIL

    if _LLM_DISABLED and time.time() < _LLM_DISABLED_UNTIL:
        return _keyword_classify(headline)
    if _LLM_DISABLED:  # cooldown elapsed — retry the LLM
        _LLM_DISABLED = False
        _LLM_FAIL_COUNT = 0
        log.info("[classifier] LLM cooldown elapsed — retrying LLM")

    has_llm_key = any([
        config.ANTHROPIC_API_KEY,
        config.OPENAI_API_KEY,
        config.OPENROUTER_API_KEY,
        config.GEMINI_API_KEY,
        config.XAI_API_KEY,
        config.GROQ_API_KEY,
    ])
    if not has_llm_key:
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
            max_tokens=1000,  # ensure room for JSON even if model includes thinking tokens
            temperature=0.0,
            messages=[
                {"role": "system", "content": "You are a prediction market news classifier. Output ONLY valid JSON, nothing else."},
                {"role": "user", "content": prompt}
            ],
        )
        text = _response_text(response)
        if not text:
            raise ValueError("LLM returned empty content and reasoning_content")
        result = _extract_json(text)
        latency = int((time.time() - start) * 1000)
        _LLM_FAIL_COUNT = 0  # a good call resets the breaker

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
            _LLM_DISABLED_UNTIL = time.time() + _LLM_COOLDOWN_SECONDS
            log.warning(
                f"[classifier] LLM failed {_LLM_FAIL_COUNT}x — cooling down for "
                f"{int(_LLM_COOLDOWN_SECONDS)}s, keyword fallback meanwhile "
                f"({type(e).__name__})"
            )
        else:
            log.warning(f"[classifier] LLM error: {e} — falling back to keywords")
        return _keyword_classify(headline)
