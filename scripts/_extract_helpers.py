"""Automated 250-line enforcement: extract functions from oversized files.

Reads each source file, identifies function boundaries, creates new helper
modules, and produces trimmed versions of the originals.
"""
from pathlib import Path
import re, textwrap

BOT = Path("d:/Github repos/Polymarket bot/bot")


# ── helpers ──────────────────────────────────────────────────────────────

def extract_functions(source: Path, names: list[str]) -> dict[str, str]:
    """Return {func_name: full_source_lines} for each requested function."""
    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    result = {}
    i = 0
    while i < len(lines):
        m = re.match(r"^(?:async\s+)?def\s+(\w+)\s*\(", lines[i])
        if m and m.group(1) in names:
            name = m.group(1)
            start = i
            i += 1
            while i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("\t") or lines[i].strip() == ""):
                i += 1
            result[name] = "".join(lines[start:i])
        else:
            i += 1
    return result


def build_removal_pattern(names: list[str]) -> re.Pattern:
    """Regex that matches function defs for the given names (top-level)."""
    alts = "|".join(re.escape(n) for n in names)
    return re.compile(
        rf"^(?:#[^\n]*\n)*"              # optional preceding comments
        rf"(?:@\w+(?:\([^)]*\))?\n)*"    # optional decorators
        rf"(?:async\s+)?def\s+(?:{alts})\s*\(.*?\).*?:\s*\n"
        rf"(?:[ \t]+[^\n]*\n|[\t ]*\n)*",  # body (indented or blank)
        re.MULTILINE,
    )


def count_lines(text: str) -> int:
    return len(text.strip().splitlines())


# ── Extraction plans ─────────────────────────────────────────────────────

PLANS = [
    # (source_file, new_file, new_file_header, [func_names])
    (
        "journal.py", "journal_stats.py",
        '''"""
Journal statistics & analytics — extracted from journal.py.

Contains: segment stats, recent results, trade history queries.
Core trade logging stays in journal.py (smaller surface for edits).
"""
from __future__ import annotations

import sqlite3

from . import config


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
''',
        ["get_segment_stats", "get_recent_trades"],
    ),
    (
        "macro.py", "macro_data.py",
        '''"""
Macro data fetchers — extracted from macro.py.

All external API calls (FRED, CoinGecko, Yahoo Finance, DeFi Llama, newsapi.ai).
Each source is independently cached (15 min TTL for most, 1h for newsapi).
"""
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
''',
        [
            "_fred_observations", "fetch_fed_rate", "fetch_cpi", "fetch_unemployment",
            "fetch_crypto_prices", "crypto_regime_score",
            "_yahoo_quote", "fetch_vix", "fetch_sp500", "fetch_gold", "vix_regime_score",
            "fetch_defi_tvl", "defi_regime_score",
            "_newsapi_fetch_keyword", "fetch_newsapi_headlines",
        ],
    ),
    (
        "markets.py", "spread.py",
        '''"""
Spread analysis — extracted from markets.py.

Fetches and filters bid-ask spreads from the CLOB order book.
Wide spreads indicate low liquidity and hidden execution cost.
"""
from __future__ import annotations

import logging

from . import config
from . import http

log = logging.getLogger(__name__)
''',
        ["fetch_spread", "fetch_batch_spreads", "filter_by_spread"],
    ),
    (
        "watcher.py", "watcher_ws.py",
        '''"""
WebSocket price streaming — extracted from watcher.py.

Handles WS connection, reconnection, message parsing, and fallback polling.
The MarketPriceWatcher class in watcher.py delegates to these functions.
"""
from __future__ import annotations

import json
import logging
import time

log = logging.getLogger(__name__)

MARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
RECONNECT_DELAY = 5.0
MAX_RECONNECT_DELAY = 60.0
HEARTBEAT_INTERVAL = 30.0
''',
        ["_run_ws", "_handle_ws_message", "_update_price", "_run_polling"],
    ),
    (
        "quant.py", "quant_signals.py",
        '''"""
Quant signal functions — extracted from quant.py.

Signal 1: Momentum (EMA crossover on price history)
Signal 2: Mean reversion (z-score vs recent distribution)
Signal 3: Order book imbalance (flow pressure)

Each returns a score in [-1, +1]. No LLM calls. Pure Python + requests.
"""
from __future__ import annotations

import math
import logging

log = logging.getLogger(__name__)
''',
        ["_ema", "momentum_signal", "mean_reversion_signal", "flow_signal"],
    ),
]


# ── Execute ──────────────────────────────────────────────────────────────

total_new_lines = 0
total_saved_lines = 0

for src_name, new_name, header, func_names in PLANS:
    src = BOT / src_name
    new = BOT / new_name

    funcs = extract_functions(src, func_names)
    found = list(funcs.keys())
    missing = [n for n in func_names if n not in funcs]

    if missing:
        print(f"  ⚠ {src_name}: missing functions: {missing}")

    # Build new file
    new_content = header + "\n" + "".join(funcs[n] for n in found)
    new.write_text(new_content, encoding="utf-8")
    new_count = count_lines(new_content)
    total_new_lines += new_count
    print(f"  ✅ {new_name}: {new_count} lines ({', '.join(found)})")

    # Build trimmed source
    original = src.read_text(encoding="utf-8")
    pattern = build_removal_pattern(func_names)
    trimmed = pattern.sub("", original)

    # Count saved
    old_count = count_lines(original)
    saved = old_count - count_lines(trimmed)
    total_saved_lines += saved
    print(f"  ✂ {src_name}: {old_count} → {count_lines(trimmed)} lines (saved {saved})")

    src.write_text(trimmed, encoding="utf-8")

print("\n=== Summary ===")
print(f"New helper lines: {total_new_lines}")
print(f"Lines removed from originals: {total_saved_lines}")

# Verify
for src_name, new_name, _, func_names in PLANS:
    src = BOT / src_name
    new = BOT / new_name
    src_count = count_lines(src.read_text(encoding="utf-8"))
    new_count = count_lines(new.read_text(encoding="utf-8"))
    status = "✅" if src_count <= 250 else "⚠️"
    print(f"  {status} {src_name}: {src_count} lines | {new_name}: {new_count} lines")
