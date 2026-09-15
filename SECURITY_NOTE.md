# Security Finding — 2026-09-15

Pylance `secrets:S7013` flagged `.env` line 66: `OPENROUTER_API_KEY=sk-or-v1-...`
Verified: 3 live secrets present in `.env`:
- Line 66: OPENROUTER_API_KEY (OpenRouter / OpenAI-compatible)
- Line 68: GEMINI_API_KEY (Google/Gemini)
- Line 89: POLYMARKET_PRIVATE_KEY (Polymarket live trading)

Status: User confirmed repo is private; instructed to leave as-is (not revoked at source).
Action taken: NONE (per user directive). Documented here for audit trail.
Recommendation: If repo ever becomes public or is shared, these MUST be revoked at
provider (OpenRouter, Google, Polymarket) and rotated — deleting from .env does NOT
invalidate the keys.
