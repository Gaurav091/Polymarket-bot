"""Central configuration — loads .env, defines survival-mode + trading parameters."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# All HTTP calls use verify=False (SSL verification hangs on this machine) —
# silence the resulting warning spam once, globally.
import urllib3  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# Survival Mode — the defining feature
# ============================================================
# If the bot earns no money (realized profit) within this window,
# it dies (halts permanently and writes a death report).
SURVIVAL_WINDOW_MINUTES = int(os.getenv("SURVIVAL_WINDOW_MINUTES", "30"))
# Grace period at startup before the survival clock starts ticking
SURVIVAL_GRACE_MINUTES = int(os.getenv("SURVIVAL_GRACE_MINUTES", "10"))
# Minimum realized profit per window to stay alive (USD)
SURVIVAL_MIN_PROFIT_USD = float(os.getenv("SURVIVAL_MIN_PROFIT_USD", "0.01"))
# When False, survival mode is disabled (bot runs forever) — for testing only
SURVIVAL_ENABLED = os.getenv("SURVIVAL_ENABLED", "true").lower() == "true"

# ============================================================
# Trading mode
# ============================================================
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
CAPITAL_USD = float(os.getenv("CAPITAL_USD", "100"))
MAX_BET_USD = float(os.getenv("MAX_BET_USD", "10"))
MIN_BET_USD = float(os.getenv("MIN_BET_USD", "3"))
EDGE_THRESHOLD = float(os.getenv("EDGE_THRESHOLD", "0.10"))
# Minimum entry price — <20c entries had 68% SL rate and -$1.96 avg PnL.
# Sub-30c entries are net-negative; above 30c the system is profitable.
# This is a hard gate enforced in _maybe_trade() — not just a market filter.
MIN_ENTRY_PRICE = float(os.getenv("MIN_ENTRY_PRICE", "0.30"))
# Per-market loss circuit breaker: after N losses on one market, block it forever
# Trip after 2 losses — the ICE-loop bled 27x but that was before the breaker.
# 1 is too aggressive (blocks 61 markets with a single historical loss); 2
# still catches revenge loops while leaving one-shot losers tradeable.
MARKET_LOSS_LIMIT = int(os.getenv("MARKET_LOSS_LIMIT", "2"))

# ============================================================
# Risk management (4-layer system, ported from Polymarket-bot)
# ============================================================
DAILY_MAX_LOSS_PCT = float(os.getenv("DAILY_MAX_LOSS_PCT", "0.05"))      # 5%
MONTHLY_MAX_LOSS_PCT = float(os.getenv("MONTHLY_MAX_LOSS_PCT", "0.15"))  # 15%
MAX_DRAWDOWN_PCT = float(os.getenv("MAX_DRAWDOWN_PCT", "0.25"))          # 25%
TOTAL_MAX_LOSS_PCT = float(os.getenv("TOTAL_MAX_LOSS_PCT", "0.40"))      # 40%

# ============================================================
# Market filters (niche-market strategy from PolyAgent)
# ============================================================
MIN_VOLUME_USD = float(os.getenv("MIN_VOLUME_USD", "1000"))
MAX_VOLUME_USD = float(os.getenv("MAX_VOLUME_USD", "500000"))
MATERIALITY_THRESHOLD = float(os.getenv("MATERIALITY_THRESHOLD", "0.65"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "5"))
# Timeout reduced from 20→12 min: timeout trades have 29.5% WR and -$40 PnL.
# Dead money should be recycled fast — 12 min is enough for a directional move.
POSITION_TIMEOUT_MINUTES = int(os.getenv("POSITION_TIMEOUT_MINUTES", "12"))
MAX_SPREAD_USD = float(os.getenv("MAX_SPREAD_USD", "0.08"))  # 8¢ max spread

# Quant engine (Python-native, free data — no LLM)
# Raised from 0.35→0.50: 35% WR at 0.35 threshold is unprofitable.
# Only fire quant signals when ensemble is genuinely confident.
QUANT_MIN_STRENGTH = float(os.getenv("QUANT_MIN_STRENGTH", "0.50"))

# TimesFM 2.5 (200M, Apache-2.0) — Google time-series foundation model.
# CPU-only on this machine: ~0.7s/market batched. Disabled by default;
# set TIMESFM_ENABLED=true in .env to activate.
TIMESFM_ENABLED = os.getenv("TIMESFM_ENABLED", "false").lower() == "true"
TIMESFM_HORIZON = int(os.getenv("TIMESFM_HORIZON", "12"))        # forecast 12h ahead
TIMESFM_MIN_HISTORY = int(os.getenv("TIMESFM_MIN_HISTORY", "30"))  # min candles needed
TIMESFM_DRIFT_SCALE = float(os.getenv("TIMESFM_DRIFT_SCALE", "8.0"))  # drift→score scale

# ============================================================
# LLM Classifier
# ============================================================
# LLM Classifier — model selection
# Primary: OpenRouter/minimax-m2.7 (MiniMax M2.7, free tier via OpenRouter)
# gemini-3.6-flash via OpenRouter is an alternative (free, 20 req/day on OpenRouter's free tier)
# Note: x-ai/grok-3-fast does NOT exist on OpenRouter — old config was broken
CLASSIFICATION_MODEL = os.getenv(
    "CLASSIFICATION_MODEL", "openrouter/minimax/minimax-m2.7:free"
)

# ============================================================
# Survival Emergency Overrides — activated when bot is critical
# ============================================================
# When the survival clock is critical (<25% time remaining),
# these overrides let the bot trade with relaxed thresholds
SURVIVAL_EMERGENCY_ENABLED = os.getenv("SURVIVAL_EMERGENCY_ENABLED", "true").lower() == "true"
CRITICAL_WINDOW_MINUTES = int(os.getenv("CRITICAL_WINDOW_MINUTES", "5"))       # time-left threshold for emergency
EMERGENCY_EDGE_THRESHOLD = float(os.getenv("EMERGENCY_EDGE_THRESHOLD", "0.02"))  # near-zero edge floor in emergency
EMERGENCY_MATERIALITY_THRESHOLD = float(os.getenv("EMERGENCY_MATERIALITY_THRESHOLD", "0.20"))  # low materiality floor

# ============================================================
# APIs
# ============================================================
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_HOST = "https://clob.polymarket.com"

# LLM provider (optional — bot falls back to keyword-only mode without it)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Macro data providers (free tiers)
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# Polymarket CLOB credentials (live trading only)
POLYMARKET_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")
POLYMARKET_API_KEY = os.getenv("POLYMARKET_API_KEY", "")
POLYMARKET_API_SECRET = os.getenv("POLYMARKET_API_SECRET", "")
POLYMARKET_API_PASSPHRASE = os.getenv("POLYMARKET_API_PASSPHRASE", "")

# News sources (RSS — works without any API keys)
RSS_FEEDS = [
    feed.strip()
    for feed in os.getenv(
        "RSS_FEEDS",
        "https://news.google.com/rss/search?q=AI+artificial+intelligence&hl=en-US&gl=US&ceid=US:en,"
        "https://news.google.com/rss/search?q=bitcoin+crypto&hl=en-US&gl=US&ceid=US:en,"
        "https://news.google.com/rss/search?q=federal+reserve+economy&hl=en-US&gl=US&ceid=US:en,"
        "https://feeds.feedburner.com/TechCrunch,"
        "https://feeds.arstechnica.com/arstechnica/technology-lab,"
        "https://www.theverge.com/rss/index.xml",
    ).split(",")
    if feed.strip()
]

# Loop cadence
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))
NEWS_POLL_SECONDS = int(os.getenv("NEWS_POLL_SECONDS", "45"))

# Polymarket taker fee rate by category (see polymarket.com/fees)
# fee = shares * feeRate * price * (1 - price)
# Default 0.04 covers Politics/Tech/Mentions; override via env
POLY_FEE_RATE = float(os.getenv("POLY_FEE_RATE", "0.04"))

# SQLite journal
DB_PATH = ROOT / "data" / "trades.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
