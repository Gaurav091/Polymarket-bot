# Auto-harvested Lessons

*Last updated: 2026-09-02  |  source: scripts/harvest_memory.py*

> This file is auto-generated. Do NOT edit manually.
> Copilot: read this before modifying any existing file.

## Known Error Patterns

| Exception | Module | Hint | Source log |
|-----------|--------|------|------------|
| `ValueError` | `sensibull_fetcher` | Check input validation in sensibull_fetcher. | stocks.log |
| `Symbol in F&O but no chain` | `config/__init__.py` `get_fno_filtered_symbols()` | stock_metadata.BY_SYMBOL has ~17 false positives not in AngelOne NFO scrip master. Use AngelOne NFO as primary source + InstrumentResolver.get_nfo_underlyings(). | scanner.log |

## Recent Fix History (git)

*Commits containing 'fix', 'bug', 'error', 'broken', 'revert', 'patch':*

- 9cdd0f2 fix(fno): use AngelOne NFO scrip master as source of truth for F&O universe
- 01719f1 ops: add daily post-fix momentum report script + VS Code tasks
- 52a83a7 position-mgmt: simplify _process_action stub (real exits live in OrderManagerMonitor)
- eb506c7 starters: remove dead CONTEXT_FILE constant and unused time import
- 9062dff risk-audit: hoist re import to top, drop unused json import
- 9be1b5f starters: remove unused os imports from triage and signal-gen
- cc8e53c M1-M3: remove urllib3/warnings anti-patterns, add open_db(), use load_yaml()
- d6f33ff fix: signal→trade→outcome linkage was born broken
- bcd603d fix: persist gate sub-reasons + unblock misfiring Greeks gates
- 36600a7 fix: Telegram notifier + DB lock + BTST gap model
- 2134cf5 fix: Escape dynamic content in Telegram formatters to prevent Markdown parse errors
- f808caa fix: orchestrator.py Optional import + quality-over-quantity verification
- 34f7b71 fix(loop): correct starter imports, TradeCard mapping, RiskManager attrs + add 5 loop workflows
- 7e3c789 fix(inspector): restore user messages in tool requests + fix tool_calls args accumulation
- a071116 fix: weekend guard before Fyers login + consistent Telegram bold for stock signals
- dcd9c36 fix: Fyers one-shot credential check — skip Playwright login if unavailable
- 87c272b fix: paper portfolio accuracy + position close notifications + compound task fix
- 2d8c472 fix(index_scanner): allow FLAT-gap indices in SECONDARY phase
- b25acdf fix: replace aiohttp/yfinance/urlopen with requests, fix macro agent tests
- 64391ef fix: stock momentum profitability — 4 targeted fixes from Aug 5 trade analysis
- e985b9a fix(index-momentum): 3 root causes of dead afternoon session
- 7950fea fix(intraday): lower TP targets to achievable intraday levels (18-25%/35-42%)
- 116c441 fix(exit_manager): reorder exit priority to fix 0 TP hit rate

## Recently Modified Files

| Commit | Files |
|--------|-------|
| 9cdd0f2 fix(fno): use AngelOne NFO scrip master as source of truth for F&O universe | `config/__init__.py`, `instrument_resolver.py`, `test_fno_filter.py` |
| dc9e2eb chore: delete 38 orphan files (tmp_*.py, test_*.py, _tp.py, stale logs) | 38 files deleted |
| 01719f1 ops: add daily post-fix momentum report script + VS Code tasks | `daily_postfix_report.py`, `daily_postfix_report.ps1`, `.vscode/tasks.json` |
| 52a83a7 position-mgmt: simplify _process_action stub | `run_position_mgmt.py` |
| e4fac9d feat: read-only trade-journal MCP server for AI clients | `mcp.json`, `journal_mcp.py` |
| d6f33ff fix: signal→trade→outcome linkage was born broken | `signal_logger.py`, `orchestrator.py`, `orchestrator_lifecycle.py` |
| bcd603d fix: persist gate sub-reasons + unblock misfiring Greeks gates | `greeks_agent.py`, `fetcher_analysis.py`, `models.py`, `orchestrator_pipeline.py` |
| 7f9c26d feat: enforce Truth Protocol across all AI agents + add 5-system plan of action | `inject_truth_protocol.py` |
| 36600a7 fix: Telegram notifier + DB lock + BTST gap model | `btst_gap_model.json`, `telegram_http.py`, `telegram_notifier.py`, `logger.py`, `fetcher_global.py`, `btst_core.py` +5 more |

## Hardcoded Platform Rules (NEVER violate)

- HTTP: ALWAYS `requests` with `timeout=10, verify=False`. NEVER `aiohttp` or `urllib` — both hang on SSL.
- PowerShell: NEVER `head`/`tail`/`grep`/`cat` — use `Get-Content`, `Select-Object`, `Select-String`.
- Market data: NEVER `yfinance` import — use Yahoo chart API via `requests` directly.
- UV installs: `uv pip install --python .venv\Scripts\python.exe <pkg>`
- After code changes: restart 3 traders (`python scripts/stop_traders.py` then re-launch).

