"""Verify .env configuration — prints masked keys only, never full values.

Tests:
1. Which env vars are populated (masked preview)
2. Polymarket CLOB auth: derive API creds from private key (real auth test, no orders)
3. LLM key: one tiny classification call (if any key present)
"""
import sys

sys.path.insert(0, r"d:\Github repos\Polymarket bot")

from bot import config  # noqa: E402


def mask(name: str, value: str) -> str:
    if not value:
        return f"{name}: NOT SET"
    preview = value[:6] + "..." + value[-4:] if len(value) > 14 else value[:4] + "..."
    return f"{name}: SET ({preview}, len={len(value)})"


print("=" * 60)
print("ENV CONFIGURATION CHECK (values masked)")
print("=" * 60)
print(mask("POLYMARKET_PRIVATE_KEY", config.POLYMARKET_PRIVATE_KEY))
print(mask("POLYMARKET_API_KEY", config.POLYMARKET_API_KEY))
print(mask("ANTHROPIC_API_KEY", config.ANTHROPIC_API_KEY))
print(mask("OPENAI_API_KEY", config.OPENAI_API_KEY))
print(mask("OPENROUTER_API_KEY", config.OPENROUTER_API_KEY))
print(mask("GEMINI_API_KEY", config.GEMINI_API_KEY))
print(mask("XAI_API_KEY", config.XAI_API_KEY))
print(f"DRY_RUN: {config.DRY_RUN} ({'PAPER - safe' if config.DRY_RUN else 'LIVE - REAL MONEY'})")
print()

# ---- Test 1: Polymarket CLOB auth (derive creds = real signature test) ----
print("=" * 60)
print("POLYMARKET AUTH TEST")
print("=" * 60)
if not config.POLYMARKET_PRIVATE_KEY:
    print("SKIP: no private key set (paper mode doesn't need one)")
else:
    try:
        from py_clob_client.client import ClobClient

        client = ClobClient(
            host=config.CLOB_HOST,
            key=config.POLYMARKET_PRIVATE_KEY,
            chain_id=137,
        )
        # Health check (no auth needed)
        ok = client.get_ok()
        print(f"Server health: {ok}")

        # Derive API creds — signs with the private key. Fails if key is invalid.
        creds = client.create_or_derive_api_creds()
        print(f"API creds derived: SUCCESS (key={creds.api_key[:8]}..., "
              f"secret={creds.api_secret[:6]}..., passphrase={creds.api_passphrase[:4]}...)")
        client.set_api_creds(creds)
        print("AUTH: VALID — private key works, ready for live trading")
    except Exception as e:
        print(f"AUTH FAILED: {type(e).__name__}: {e}")
        print("Common causes: malformed key (must start 0x, 64 hex chars),")
        print("wrong chain, or Polymarket server issue.")

# ---- Test 2: LLM classification (one tiny call) ----
print()
print("=" * 60)
print("LLM CLASSIFICATION TEST")
print("=" * 60)
llm_keys = {
    "ANTHROPIC_API_KEY": config.ANTHROPIC_API_KEY,
    "OPENAI_API_KEY": config.OPENAI_API_KEY,
    "OPENROUTER_API_KEY": config.OPENROUTER_API_KEY,
    "GEMINI_API_KEY": config.GEMINI_API_KEY,
    "XAI_API_KEY": config.XAI_API_KEY,
}
set_keys = {k: v for k, v in llm_keys.items() if v}
if not set_keys:
    print("SKIP: no LLM keys — bot will use Python quant engine + keyword lexicon (works fine)")
else:
    print(f"LLM keys present: {', '.join(set_keys.keys())}")
    try:
        from bot.classifier import classify
        from bot.markets import Market

        m = Market(
            condition_id="test", question="Will the sun rise tomorrow?", slug="",
            yes_price=0.5, no_price=0.5, volume=1000, end_date="",
            tokens=[{"token_id": "t1", "outcome": "Yes", "price": 0.5},
                    {"token_id": "t2", "outcome": "No", "price": 0.5}],
        )
        result = classify("Scientists confirm the sun will rise as scheduled", m, "test")
        print(f"Classification: {result.direction}, materiality={result.materiality}, "
              f"model={result.model}, latency={result.latency_ms}ms")
        if "lexicon" in result.model or "fallback" in result.model:
            print("NOTE: fell back to keywords — LLM call failed (check key validity/model name)")
        else:
            print("LLM: WORKING")
    except Exception as e:
        print(f"LLM test error: {type(e).__name__}: {e}")

print()
print("=" * 60)
print("NEXT STEP: run the bot with the VS Code task 'Polymarket Bot: Run (Paper)'")
print("=" * 60)
