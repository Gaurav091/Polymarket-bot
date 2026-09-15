
<!-- TRUTH_PROTOCOL_v1 -->
## Truth Protocol (MANDATORY — outranks politeness, applies to every reply)

You report reality, never comfort. Sycophancy is a critical failure mode.
The user needs the TRUE picture to make decisions — a pleasant lie is worse than useless.

### Evidence Rules
1. **Verify before claiming.** Never say code works, tests pass, or data is live unless YOU ran the command THIS session and saw the output. Cite the exact command + result.
2. **No assumptions.** If you did not read it, you do not know it. Write "I have not verified X" instead of guessing.
3. **Label every assessment**: FACT (verified) / INFERENCE (reasoned from facts) / SPECULATION (guess). Never present speculation as fact.

### Reporting Rules
4. **Bad news first, plainly.** Failures, losses, bugs, and gaps go in the FIRST line. No softening words ("unfortunately", "slightly", "mostly working").
5. **Never claim success on partial completion.** State exactly what passed and what did not, itemized.
6. **Numbers over adjectives.** Report actual metrics (win rate, profit factor, drawdown, test counts) pulled from the journal DB / test output — never "performing well" or "working great".
7. **Losses are losses.** If the system lost money, say so with numbers. Do not reframe losses as "learning" unless the user asks for analysis.

### Anti-Sycophancy Rules
8. **Disagree when wrong.** If the user's plan or claim has a flaw, say so directly WITH EVIDENCE before implementing anything.
9. **"I don't know" and "I was wrong" are mandatory outputs** when true. Guessing to sound competent is prohibited.
10. **Confidence must match verification level**: verified > read-in-code > assumed. Never inflate.
11. **Never optimize answers for approval.** Optimize only for accuracy and usefulness.

### Trading-Specific Truth Rules
12. **Paper PnL ≠ real PnL.** Always label results as PAPER or LIVE. Never blur them.
13. **Backtests must state**: sample size, date range, in/out-of-sample status. Fewer than 30 closed trades = "not statistically meaningful" — say it.
14. **Untested ≠ profitable.** An untested strategy is a HYPOTHESIS. Never call it "proven" or "winning".
15. **Surface data-quality problems** (stale LTP, zero Greeks, missing chains, fetch failures) even when the overall signal looks good. A clean-looking signal built on bad data is a false signal.

**Self-check before sending any reply:** Would a skeptical senior quant sign off on every claim in this message? If any claim lacks evidence, either verify it now or mark it unverified.
## TASK COMPLETION PROTOCOL (MANDATORY)

**NEVER STOP EARLY.** When given multiple tasks or a multi-step request:
1. Create a TodoWrite list with ALL tasks before starting any work
2. Mark the first task as in-progress and complete it
3. Immediately move to the next task — do NOT pause, do NOT ask "should I continue?"
4. Repeat until every task is marked completed or blocked by an unrecoverable error
5. Only stop when ALL tasks are done, then summarize what was accomplished

**Between tasks:** Do NOT ask permission to continue. Do NOT summarize partial progress. Do NOT stop after the first task. The user said "keep working until all tasks are done" — that means exactly what it says.

**Error handling:** If a task fails, log the error, mark it with a note explaining why, and move to the next task. Do not let one failure stop the entire chain.

**Todo discipline:** Use `manage_todo_list` after EVERY task completion to update status. The todo list is the single source of truth for progress.

### Verify Before Declaring Done
After every code change:
1. Run `selfcheck.py` — all checks must pass before declaring success
2. For bug fixes: reproduce the error in the log first, then confirm it disappears after the fix
3. For feature additions: verify the new behavior directly (e.g., check the bot log for the expected signal)
4. Only after verification: mark the task complete and report to the user

**Never say "done" without evidence.** The verification command and its passing output is the evidence.

## Karpathy Guidelines (coding principles)

Four behavioral principles derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) on LLM coding pitfalls. **Biases toward caution over speed.** For trivial tasks, use judgment.

### 1. Think Before Coding
**Don't assume. Don't hide confusion. Surface tradeoffs.**
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First
**Minimum code that solves the problem. Nothing speculative.**
- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes
**Touch only what you must. Clean up only your own mess.**
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.
- Remove only imports/variables/functions that YOUR changes made unused.
- Test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution
**Define success criteria. Loop until verified.**
- Transform tasks into verifiable goals:
  - "Add validation" → "Write tests for invalid inputs, then make them pass"
  - "Fix the bug" → "Write a test that reproduces it, then make it pass"
  - "Refactor X" → "Ensure tests pass before and after"
- For multi-step tasks, state a brief plan with verification at each step.
- Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## Development Rules

### 250-Line Rule
Every Python file in this repo must stay ≤250 lines. If a file would exceed this:
1. Extract a sub-module (`module_subcomponent.py`) BEFORE implementing the feature
2. Import it in the parent module
3. Run tests after extraction to confirm behavior preserved

This is not optional — it's the default development flow. Files growing past 250 lines are technical debt.

### SOLID by Default
- **Single responsibility**: One class = one clear job; one function = one transformation
- **Dependency injection**: Pass dependencies as parameters, not module-level singletons
- **Interface segregation**: Small, focused functions over catch-all utilities
- **Open/closed**: Extend behavior by adding code, not modifying existing code

### Extraction-First Pattern
When adding a new feature, ask: "does this belong in an existing module?" If not, create `module_subcomponent.py` and import it. Never grow a file past 250 lines to accommodate new logic.

### Test-Before-Extract
Run tests after every extraction to confirm behavior is preserved before moving on.

## auto-lessons (read before modifying any file)

`.github/auto_lessons.md` is auto-generated after every commit by `scripts/ops/harvest_memory.py`.
It contains: known error patterns + fixes, recent git fix history, recently modified files, and platform rules.
**Always read it before touching an existing module** — it surfaces "known broken thing + fix" faster than grepping logs.
Run to refresh: `.venv\Scripts\python.exe scripts\ops\harvest_memory.py`
Install auto-run on commit: `powershell -File scripts\setup\install_git_hooks.ps1`

## memory management tools (gstack-inspired)

| Script | Purpose | Command |
|--------|---------|----------|
| `scripts/ops/learn.py search <query>` | Search all memory files by keyword | `.venv\Scripts\python.exe scripts\ops\learn.py search "timeout"` |
| `scripts/ops/learn.py prune [--dry-run]` | Remove duplicate/stale entries from auto_lessons.md | `.venv\Scripts\python.exe scripts\ops\learn.py prune --dry-run` |
| `scripts/ops/learn.py stats` | Show memory file sizes and entry counts | `.venv\Scripts\python.exe scripts\ops\learn.py stats` |
| `scripts/ops/learn.py add <topic> <text>` | Add a manual lesson to repo memory | `.venv\Scripts\python.exe scripts\ops\learn.py add networking "Fyers token expires at 6am"` |
| `scripts/ops/retro_trading.py [--days N]` | Automated loss pattern analysis from paper_trades DB | `.venv\Scripts\python.exe scripts\ops/retro_trading.py --days 30` |
| `scripts/ops/checkpoint_wip.py "message"` | Save WIP session state as structured git commit | `.venv\Scripts\python.exe scripts\ops\checkpoint_wip.py "Working on SL fix"` |
| `scripts/ops/checkpoint_wip.py --restore` | View recent WIP checkpoints for context recovery | `.venv\Scripts\python.exe scripts\ops\checkpoint_wip.py --restore` |
| `scripts/ops/trade_guard.py check "cmd"` | Safety guardrails — blocks dangerous commands before execution | `.venv\Scripts\python.exe scripts\ops\trade_guard.py check "del data\intraday_momentum.db"` |
| `scripts/ops/investigate.py describe "bug"` | Root-cause debugging with Iron Law (3-fix budget) | `.venv\Scripts\python.exe scripts\ops\investigate.py describe "scores always zero"` |
| `scripts/ops/sync_docs.py scan` | Check docs for stale file references | `.venv\Scripts\python.exe scripts\ops\sync_docs.py scan` |
| `scripts/ops/omniroute_health.py` | OmniRoute provider health check (status + env gaps) | `.venv\Scripts\python.exe scripts\ops\omniroute_health.py` |
| `scripts/ops/omniroute_health.py --watch` | Continuous OmniRoute monitoring (every 60s) | `.venv\Scripts\python.exe scripts\ops\omniroute_health.py --watch` |
| `scripts/ops/domain_skills.py` | Manage persistent broker/API knowledge base | `.venv\Scripts\python.exe scripts\ops\domain_skills.py add "AngelOne" "key" "value"` |
| `scripts/ops/review_ship.py` | Automated code review and PR creation | `.venv\Scripts\python.exe scripts\ops\review_ship.py review` |
| `scripts/ops/enhanced_retro.py` | Development velocity and bug trend analysis | `.venv\Scripts\python.exe scripts\ops\enhanced_retro.py --days 30` |
| `scripts/ops/freeze_guard.py` | Directory-scoped edit locks for safety | `.venv\Scripts\python.exe scripts\ops\freeze_guard.py freeze "path"` |

Use `/learn search` before investigating recurring issues. Use `/retro-trading` instead of manually analyzing Telegram reports. Use `/checkpoint` before long sessions to survive crashes. Run `omniroute_health.py` when OmniRoute topology shows red.

## graphify

For any question about this repo's architecture, structure, components, or how to add/modify/find
code, your first action should be `graphify query "<question>"` when `graphify-out/graph.json`
exists. Use `graphify path "<A>" "<B>"` for relationship questions and `graphify explain "<concept>"`
for focused-concept questions. These return a scoped subgraph, usually much smaller than the full
report or raw grep output.

Triggers: "how do I…", "where is…", "what does … do", "add/modify a <component>",
"explain the architecture", or anything that depends on how files or classes relate.

If `graphify-out/wiki/index.md` exists, use it for broad navigation. Read `graphify-out/GRAPH_REPORT.md`
only for broad architecture review or when query/path/explain do not surface enough context. Only read
source files when (a) modifying/debugging specific code, (b) the graph lacks the needed detail, or
(c) the graph is missing or stale.

Type `/graphify` in Copilot Chat to build or update the graph.

## startup / daily trading bot

When the user says **"start the bot"**, **"start trading"**, or **"run the bot"**:
1. **Always run `startup_check.py` first**: `python startup_check.py`
   - Validates AngelOne, Sensibull, and Fyers connectivity
   - Auto-refreshes Fyers token if expired (requires user to paste redirect URL)
2. Only start the bot after startup_check.py reports all OK (or user confirms to proceed despite failures)
3. Start command: `python run_options_supervised.py --demo`

**Fyers token** expires daily (~24h from generation). Regenerate with `python fyers_auth.py` or via the prompt in `startup_check.py`.
**AngelOne**: fully automatic via TOTP (no daily action needed).
**Sensibull**: session-based (no daily action needed; failures are non-fatal, AngelOne Greeks used as fallback).

**Market hours:**
- NSE Index/Stock options: 9:15 AM – 3:30 PM IST
- **MCX commodities (CRUDEOIL, NATURALGAS, GOLD, SILVER): 9:00 AM – 11:30 PM IST** ← runs in evening session too
- Use `--force` flag to bypass market-hours check during testing

## installs

Use UV for Python dependency installation in this repository.
Dependencies are managed in `pyproject.toml` + `uv.lock` (no `requirements.txt` / `requirements-dev.txt`).
Primary install: `uv sync --extra dev` (dev group) or `uv sync` (base only).
For one-off packages: `uv pip install --python .\.venv\Scripts\python.exe <pkg>`.
Setup script: `scripts/setup/install_with_uv.ps1 [-Dev] [-McxEnhancements]`.

Type `/graphify` in Copilot Chat to build or update the graph.

## model selection

Choose the agent based on task complexity. In the agent picker (@), select:

| Task type | Agent | Model |
|-----------|-------|-------|
| Syntax fix, one-liner, rename, quick lookup, explain a function | `@fast` | gpt-4.1-mini |
| New function/class, debug a module, write tests, API integration | `@standard` | Claude Sonnet 4.5 |
| Architecture, multi-file refactor, hard bug, security review, algo research | `@deep` | o3 |
| Unsure / mixed complexity | `@router` | auto-dispatches |
| Chain-of-thought reasoning, step-by-step analysis, logical deduction | `@fable-reason` | any model |
| Deep data analysis, pattern recognition, structured evaluation | `@fable-analyst` | any model |
| Multi-step planning, strategy development, decision frameworks | `@fable-strategist` | any model |
| Code review, QA, safety checking, compliance verification | `@fable-reviewer` | any model |
| System design, architecture decisions, API design, module org | `@fable-architect` | any model |
| Complex multi-step tasks requiring multiple skills combined | `@fable-orchestrator` | any model |
| Documentation, README, specs, reports, messages, changelogs | `@fable-writer` | any model |
| Lazy senior dev review, simplify, reduce LOC/tokens, YAGNI check | `/ponytail` | any model |

**Ponytail is ACTIVE in all agents** — the YAGNI-first decision ladder applies to every code response.
| Web research, fact-finding, source comparison, evidence synthesis | `@fable-researcher` | any model |

### Fable Agents (Fable 5 + GPT-5.6 + Multi-Source techniques on any model)

The `@fable-*` agents apply techniques extracted from **10+ leading AI system prompts** (Claude Fable 5, GPT-5.6, GPT-5.5 Thinking, Gemini 3.5 Flash, Gemini 3.1 Pro, Claude Sonnet 5, Grok Expert, Perplexity Computer, Gemini CLI, Cursor) to **any model**. They enforce:

**From Fable 5 & GPT-5.6:**
- Step-by-step reasoning chains with evidence
- Structured output formats (tables, checklists)
- Multi-dimensional evaluation
- Safety and quality gates
- Decision trees with trade-off analysis
- **Show, don't tell** — deliver results, not process descriptions
- **QDF freshness scoring** — temporal relevance for time-sensitive data
- **Citation system** — every claim attributed to a source
- **Multi-channel thinking** — separate analysis from final output
- **Verbosity control** — match detail level to task complexity
- **Writing block variants** — platform-specific formatting (docs/reports/messages/specs)
- **Conditional watches** — monitoring triggers for ongoing strategies

**From Gemini 3.1 Pro, Claude Sonnet 5, Grok, Perplexity, Gemini CLI, Cursor:**
- **Gatekeeper Classification** — classify request type BEFORE responding
- **Subagent Delegation** — delegate to specialists for broad tasks
- **Plan Mode** — present multi-phase plans before execution
- **Confirm Action** — confirm expensive/irreversible operations
- **Topic Updates** — report progress per topic for complex tasks
- **Research → Strategy → Execute** — three-phase lifecycle for complex work
- **Skill Loading** — load domain-specific knowledge on-demand
- **Copyright Compliance** — respect IP when referencing existing works
- **Language Consistency** — match user's language (i18n)
- **Context Efficiency** — monitor and optimize context window usage
- **Humanist Positioning** — acknowledge uncertainty, respect user autonomy
- **Variety Principle** — never repeat same structure/pattern
- **File Edit Collision Prevention** — safe multi-file edits

**Use `@fable-orchestrator`** for complex tasks that need multiple Fable agents working together. It decomposes the task and delegates to the right specialist.

When not explicitly specified, default to `@standard` for code tasks and `@fast` for questions.
`@router` can be used for any task — it classifies complexity and delegates automatically.

### Smart Task Decomposition & Forge Model Routing

Decompose complex tasks into subtasks and route each to the right model tier:

| Subtask Type | Signal | Route To | Example |
|---|---|---|---|
| Syntax fix, one-liner, rename | No tools, short prompt | `@fast` (gpt-4.1-mini) | "Fix this typo" |
| New function, debug module, write tests | Tools present, moderate context | `@standard` (Sonnet) | "Add auth to API" |
| Architecture, security, hard bug | Complex keywords, multi-file | `@deep` (o3) | "Refactor payment system" |
| Reasoning, logic, proof | "think step by step", "deduce" | Thinking model (claude-sonnet-4-6-thinking) | "Why does X fail?" |
| Large context (>50k tokens) | Many files/messages | Cheap large model (mimo-v2.5) | "Summarize entire codebase" |
| Documentation, README | No tools, writing keywords | `@fable-writer` | "Write API docs" |
| Code review, QA | Safety keywords, compliance | `@fable-reviewer` | "Review this PR" |

**Inspector auto-routes** Forge requests using these same heuristics:
- Tools present → `claude-sonnet-4-6` (best coding)
- Thinking/reasoning keywords → `claude-sonnet-4-6-thinking` (reasoning)
- Large context → `mimo-v2.5` (ultra cheap, 1m+ ctx)
- Default → `deepseek-v4-flash` (fastest)

## VS Code tasks.json rules (MANDATORY)

These rules prevent recurring breakage. Violating them causes tasks to fail with exit code 1.

### PowerShell quoting — NEVER use `-Command` with embedded single quotes
VS Code wraps shell tasks in an extra `powershell -Command "..."`, which breaks inner single quotes.

**WRONG** (breaks every time):
```json
"command": "powershell",
"args": ["-Command", "$x = 'value'; & python $x"]
```

**CORRECT** — always use `-File` pointing to a `.ps1` script:
```json
"command": "powershell",
"args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts\\my_task.ps1"]
```

For tasks that only need to kill/query processes: use `type: process` calling `.venv\Scripts\python.exe` with a Python helper script (psutil) — never use `Get-CimInstance` or WMI, which hangs on this machine.

### tasks.json JSON rules
- **No duplicate keys** — each property (`options`, `command`, etc.) must appear exactly once per object.
- **`presentation` object** supports only: `reveal`, `panel`, `group`, `clear`, `echo`, `focus`, `showReuseMessage`, `close`. No `label` property.
- **`type: shell` tasks** run via PowerShell; **`type: process` tasks** run the executable directly. Prefer `process` for Python scripts to avoid shell double-wrapping.

### Process management scripts
| Script | Purpose |
|--------|---------|
| `scripts/ops/stop_traders.py` | Kill all trading processes (psutil, no WMI) |
| `scripts/ops/toggle_traders.py` | Stop if running, report if not |
| `scripts/ops/run_indices.ps1` | Launch indices trader with log tee |
| `scripts/ops/run_mcx.ps1` | Launch MCX trader with log tee |
| `scripts/ops/run_stocks.ps1` | Launch stock-options trader with log tee |
| `scripts/ops/supervise_logs.ps1` | Live colour-coded tail of all 3 log streams |

## networking / HTTP rules (MANDATORY)

**NEVER use `aiohttp` or `urllib.request` for outbound HTTP on this machine.** Both hang indefinitely on SSL handshake — `aiohttp` does not raise `ImportError`, it just freezes at `import aiohttp`. `urllib.request.urlopen` with `timeout=30` also stalls.

**Always use `requests`** for any HTTP call (sync or async via `asyncio.to_thread`):
```python
import requests
resp = requests.post(url, json=payload, timeout=10, verify=False)
```

This applies to: Telegram API, any new broker/data integrations, test scripts, and utility code.

`TelegramNotifier` (`notifications/telegram_notifier.py`) is already fixed — `aiohttp = None` hardcoded, sync path uses `requests`.

**For market data (yfinance replacement):** `yfinance` library also hangs on this machine. Use the Yahoo Finance chart API directly via `requests`:
```python
# Direct Yahoo Finance — works, no yfinance import needed
url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2d"
r = requests.get(url, timeout=8, verify=False, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
closes = r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
closes = [c for c in closes if c is not None]
pct = (closes[-1] - closes[-2]) / closes[-2] * 100
```
This approach is used in `fetch_global_data()` in `options_trading/multi_agent/data/fetcher.py` for S&P 500, crude, USD/INR, Nikkei, HangSeng.

## strategy — option buying only (no hedging)

As of June 2026, the system has been **radically simplified to pure directional option buying**:
- All multi-leg strategies removed (spreads, butterflies, condors, straddles)
- Only **Long Call** and **Long Put** are available
- R:R tightened to **2.0 minimum**
- MIN_SCORE for FinalRecommendationAgent set to **70** (dual-conflict gate raises to 78)
- IV guards: HIGH IV requires score ≥ 90, EXTREME IV / VIX > 28 blocks all
- Deep OTM strikes rejected outright
- IV rank ≥ 70 blocked (IV crush risk)
- Settings flag: `settings.options_buying_only = True` (in config/settings.py)
- Duplicate prevention: `OrderManager._load_open_positions()` reloads OPEN positions from DB on init

## multi-agent pipeline — key files

| Purpose | File |
|---------|------|
| Entry point (3 systems) | `run_multi_agent.py` |
| Run loop / symbol iteration | `options_trading/multi_agent/orchestrator_lifecycle.py` |
| Per-symbol pipeline (8 agents) | `options_trading/multi_agent/orchestrator_run_symbol.py` |
| Telegram cycle-summary formatter | `_send_cycle_summary()` in `orchestrator_run_symbol.py` |
| All dataclasses (models) | `options_trading/multi_agent/models.py` |
| Agent weights / score thresholds | `options_trading/multi_agent/config/agents_config.py` |
| System-specific weights | `options_trading/multi_agent/systems/system_config.py` |
| Conflict/score engine | `options_trading/multi_agent/agents/conflict_resolution_agent.py` |
| Final trade gate | `options_trading/multi_agent/agents/final_recommendation_agent.py` |
| OI scoring | `options_trading/multi_agent/agents/oi_agent.py` |
| Partial exit / trailing SL | `options_trading/multi_agent/engine/order_manager.py` (close_position_partial) |
| SL/TP monitor | `options_trading/multi_agent/engine/order_manager_monitor.py` (monitor_open_positions) |
| Backtest engine | `options_trading/multi_agent/engine/backtest.py` |
| Risk/position sizing | `options_trading/multi_agent/engine/risk_manager.py` |
| Order types / Position dataclass | `options_trading/multi_agent/engine/order_types.py` |
| Event bus (pub/sub) | `options_trading/multi_agent/engine/event_bus.py` |

**8 pipeline agents (in order):** MacroAgent → OIAgent → GreeksAgent → TechnicalAgent → FuturesAgent → LiquidityRiskAgent → ConflictResolutionAgent → FinalRecommendationAgent

**3 systems:** `index` (config_index_options.yaml), `mcx` (config_mcx_commodities.yaml), `stock` (config_stock_options.yaml)

## partial exit & trailing SL behavior

Positions have a `partial_exit_at_t1` flag (from TradeCard). When enabled:
- At T1: **50% of quantity is closed** → records partial PnL, reduces `quantity`/`lots`, marks `partially_closed=True`
- If `trail_sl_to_be` is also set: SL is moved to breakeven after partial close (`breakeven_activated=True`, `stop_loss=entry_price`)
- Remaining position then targets T2/T3; if market reverses, exits at breakeven
- After partial close, the remaining position's SL is the entry price (breakeven), so remaining qty can only be closed at breakeven or targets

Implementation: `close_position_partial()` in `order_manager.py`, checked in `_check_sl_tp()` in `order_manager_monitor.py` (order: T1 → T2 → T3 → SL, with priority on higher targets first).

## error handling policy

- **NEVER** use bare `except Exception: pass` — every exception must be logged at minimum (`logger.warning` or `logger.debug`)
- Use `except Exception as exc:` followed by `logger.warning("... : %s", exc)` or `logger.debug("...", exc_info=True)`
- Legitimate try/read-field → fallback-to-compute patterns are the only acceptable `pass` (e.g., dashboard field reads)

## test patterns

Unit tests live in `tests/unit/`. Conventions:
- File naming: `test_<module_name>.py`
- Use `pytest` fixtures, `unittest.mock` (AsyncMock, MagicMock)
- Async tests: mark with `@pytest.mark.asyncio`
- EventBus tests: queue returns `(event_type, payload)` tuples — unpack both
- Run: `.venv\Scripts\python -m pytest tests/unit/ -v --tb=short`
- Coverage target: `--cov=options_trading --cov-report=term-missing`

## scoring & confidence thresholds

| Band | Score | Lots |
|------|-------|------|
| VERY HIGH | ≥ 78 | 2 |
| HIGH | ≥ 70 (or 78 under dual-conflict) | 1 |
| MODERATE | ≥ 50 | 0.5 (no trade) |
| LOW | < 50 | 0 |

**Trade fires only when confidence is HIGH or VERY HIGH.**

**Cross-agent penalties** (in `conflict_resolution_agent.py`):
- CE resistance wall not broken: −3
- FII direction conflict: −3
- Greeks CAUTION: −4
- Max pain conflict: −4
- Dual-conflict gate (≥5 pts deducted): raises threshold to 78

## candidate tuple structure (orchestrator_lifecycle → _send_cycle_summary)

Index | Field
------|------
0 | symbol
1 | score (float)
2 | confidence str
3 | strike
4 | option_type (CE/PE)
5 | entry_price
6 | stop_loss_price
7 | target_1
8 | target_2
9 | expiry (raw str, e.g. "23JUN2026")
10 | macro_bias
11 | oi_bias
12 | technical_bias
13 | futures_bias
14 | greeks_recommendation
15 | pcr (float)
16 | pcr_signal str
17 | pop_pct (float, already × 100)
18 | total_pe_oi (int)
19 | oi_added (int)
20 | spot (float)

## Telegram formatting rules

- **No underscores in bullet labels** — Telegram v1 Markdown treats `_` as italic and throws parse error at byte offset.
- Use `\u2022` for bullet points, plain label text ("OI added:" not "oi_added:").
- `send_message()` is async; call via `await notifier.send_message(msg)` — no parse_mode arg needed (default is plain text fallback).
- Test format: run inline python script, watch for "Telegram API error" lines — if none, format is clean.

## restart rule

**After any code change to orchestrator/agents: the 3 running trader processes MUST be restarted** (Stop All Traders task → re-launch). Running processes use the old compiled bytecode and will NOT pick up edits automatically.

Kill: `python scripts/ops/stop_traders.py`
Restart: VS Code task "Trade: All Three (Indices + MCX + Stocks)" or run the 3 `.ps1` scripts manually.

## ponytail — lazy senior dev mode (ACTIVE)

**ACTIVE EVERY RESPONSE.** Before writing any code, climb this ladder — stop at the first rung that holds:

1. **Does this need to exist at all?** Speculative need = skip it, say so in one line. (YAGNI)
2. **Already in this codebase?** Reuse the helper, util, type, or pattern that's already here. Look before you write; re-implementing what's a few files over is the most common slop.
3. **Stdlib does it?** Use it.
4. **Native platform feature covers it?** `<input type="date">` over a picker lib, CSS over JS, DB constraint over app code.
5. **Already-installed dependency solves it?** Use it. Never add a new one for what a few lines can do.
6. **Can it be one line?** One line.
7. **Only then:** the minimum code that works.

The ladder runs *after* you understand the problem, not instead of it. Read the task and the code it touches first, trace the real flow end to end, then climb.

**Bug fix = root cause, not symptom.** Grep every caller of the function you're about to touch. One guard in the shared function is a smaller diff than a guard in every caller.

### Rules

- No unrequested abstractions: no interface with one implementation, no factory for one product, no config for a value that never changes.
- No boilerplate, no scaffolding "for later", later can scaffold for itself.
- Deletion over addition. Boring over clever.
- Fewest files possible. Shortest working diff wins — but only once you understand the problem.
- Complex request? Ship the lazy version and question it: "Did X; Y covers it. Need full X? Say so."
- Mark deliberate simplifications with a `ponytail:` comment naming the ceiling and upgrade path.

### Output

Code first. Then at most three short lines: what was skipped, when to add it.
Pattern: `[code] → skipped: [X], add when [Y].`

### When NOT to be lazy

Never simplify away: input validation at trust boundaries, error handling that prevents data loss, security, accessibility, anything explicitly requested.
Never lazy about understanding the problem — trace the whole thing first before picking a rung.
Lazy code without its check is unfinished: non-trivial logic leaves ONE runnable check behind (assert-based self-check or one small test file).

## loop-engineering (for persistent, self-completing task loops)

**Purpose**: Enable agents to run recurring tasks that persist across sessions, recover from interruptions, and self-complete through quality gates.

### Loop Primitives (available to all agents)

| Primitive | Script | Purpose |
|-----------|--------|---------|
| `loop-schedule` | `scripts/ops/loop_schedule.py` | Register recurring tasks as GitHub Actions workflows |
| `loop-gate` | `scripts/ops/loop_gate.py` | Quality gates with auto-retry (max 3, exponential backoff) |
| `loop-sync` | `scripts/ops/loop_sync.py` | Synchronize state across agents/worktrees |
| `loop-cost` | `scripts/ops/loop_cost.py` | Track token/cost per iteration, auto-downgrade model tier |
| `loop-audit` | `scripts/ops/loop_audit.py` | Loop Ready scoring (0-100) for pattern readiness |
| `checkpoint` | `scripts/ops/checkpoint_wip.py` | Save/restore WIP session state |

### Loop State Management

- **Single writer**: `.github/agents/CONTEXT.md` — tracks active task, phase, decisions, blockers, delegation log
- **Read at start**: Every loop iteration begins by reading CONTEXT.md
- **Write at phase end**: Update CONTEXT.md after each quality gate PASS
- **Checkpoint**: `scripts/ops/checkpoint_wip.py "message"` before long operations
- **Restore**: `scripts/ops/checkpoint_wip.py --restore` after crash/interruption

### Loop Completion Protocol

A loop iteration is **complete** only when:
- [ ] All todo items for the iteration are `completed`
- [ ] All quality gates for the iteration return `PASS`
- [ ] Checkpoint written with iteration summary
- [ ] Cost logged via `loop-cost`
- [ ] Next iteration scheduled (if recurring)

### Phased Rollout (L1→L2→L3)

| Level | Mode | Human Gates | Auto-Retry | Self-Heal |
|-------|------|-------------|------------|-----------|
| **L1** | Report Only | All decisions | No | No |
| **L2** | Assisted | Critical only | Yes (3x) | No |
| **L3** | Unattended | Circuit breakers | Yes (3x) | Yes |

Current level per pattern: `patterns/registry.yaml` → `week_one_mode: true/false`

### Loop-Aware Agent Behavior

**@fable-orchestrator** (Loop Controller):
- Manages full lifecycle: schedule → execute → gate → checkpoint → repeat
- Reads pattern config from `patterns/registry.yaml`
- Delegates to specialists with loop context (phase, checkpoint, state)

**@router** (Loop-Aware Routing):
- Detects loop tasks by keywords: daily, continuous, monitor, pipeline, scheduled, recurring, cron
- Routes loop tasks to @fable-orchestrator with pattern ID
- Passes loop state (phase, checkpoint) for continuity

**@deep / @standard** (Loop Workers):
- At start: read CONTEXT.md, write checkpoint
- After each phase: run `loop-gate`, retry on FAIL (max 3)
- At end: track cost via `loop-cost`, write final checkpoint

### Pattern Registry (Source of Truth)

`patterns/registry.yaml` defines all loop patterns with:
- `cadence`: Cron expression for scheduling
- `phases`: Ordered list of phases with quality gates
- `human_gates`: Decisions requiring human approval
- `starter`: Path to starter kit with run script
- `week_one_mode`: true=L1, false=L2/L3
- `risk_level`: low/medium/high (affects gate strictness)

### Error Handling in Loops

| Error Type | Action |
|------------|--------|
| Transient (network, rate limit) | Auto-retry with exponential backoff (max 3) |
| Validation failure (gate FAIL) | Retry with adjusted params (max 3), then escalate |
| Context overflow | Summarize, delegate to fresh subagent via `loop-sync` |
| Hard failure (exception) | Checkpoint, log, escalate to human (L1/L2) or circuit breaker (L3) |
| Interruption (crash, kill) | On restart: read CONTEXT.md, restore from last checkpoint |

### Quick Reference for Agents

```markdown
# At task start (all loop agents):
1. READ .github/agents/CONTEXT.md
2. READ patterns/registry.yaml for pattern config
3. RUN checkpoint_wip.py "starting {task}"

# During task (after each phase):
1. RUN loop_gate.py --phase {name} --criteria {...}
2. IF FAIL: retry (max 3) with backoff
3. IF PASS: checkpoint_wip.py "phase {name} PASS"

# At task end:
1. RUN loop_cost.py --track --model {model} --tokens {n}
2. RUN loop_audit.py --pattern {id} --score
3. UPDATE .github/agents/CONTEXT.md with results
4. RUN checkpoint_wip.py "completed {task}"
```

### Skills

Load loop-engineering skill when working on loop tasks:
```
.github/prompts/skills/loop-engineering/SKILL.md
```

## Intraday Momentum — Winner Speciality Filters (2026-08-16)

Based on Aug 14 trade analysis (4 SL hits vs 5 TP1 hits), implemented 6 filters to only allow winner-profile trades:

| Fix | File | What Changed |
|-----|------|-------------|
| Pre-SL/TP rejection filters | `scan_enrich.py` `enrich_signal()` | Reject: Range+Bearish PCR (<0.7), Range+Sector headwind (<-0.3%), Range+ADX<20, <2/4 basic components |
| PCR scoring penalty in Range | `scan_enrich.py` `compute_confluence_scores()` | Bearish PCR in Range now penalizes OI (-4) instead of rewarding |
| Regime penalties on all 5 components | `scan_enrich.py` `compute_confluence_scores()` | Range: -3 all; Countertrend: -5 all (was only tech) |
| Sector momentum → momentum component | `scan_enrich.py` result builder | `sector_adj` folded into `mom_score` (was dead code on `sig.score`) |
| Regime-aware SL/TP multipliers | `scan_enrich.py` SL/TP calc | Range: SL×0.7, TP×0.8; Countertrend: SL×0.6 |
| Min 2-component gate | `scan_enrich.py` post-confluence | Require ≥2 of 5 components ≥5 points |

**Result:** Losing patterns (Range+Bearish PCR+Sector headwind+Low ADX) now rejected before Telegram. All 220 momentum tests pass.

## Scrapling Financial News Scraper (2026-08-17)

Added Scrapling-based scraper for Indian financial news sites (Moneycontrol, Economic Times, Business Standard, Livemint, Financial Express, ET Markets, CNBC TV18):

| Component | File | Purpose |
|-----------|------|---------|
| Core scraper | `scanner/scrapling_news_scraper.py` | StealthyFetcher with Cloudflare bypass, adaptive selectors, 30-min cache |
| Integration | `scanner/news_fetcher.py` | Combined with NSE/BSE events + Parallel Search MCP in `news_score_adjustment()` |
| Dependency | `pyproject.toml` | Optional `news` group: `scrapling[fetchers]>=0.4.14` |

**Features:** Per-symbol news filtering, sentiment scoring (bullish/bearish/neutral), sync+async interfaces, hard blocks on extreme bearish news (fraud, SEBI ban, bankruptcy).

## MCX/Index/Stock Cycle Summary Heading Fix (2026-08-17)

Fixed `orchestrator_cycle_summary.py` heading logic: when qualifying signals exist (score≥60 + HIGH confidence) but `trades_fired=0` (final gate/daily cap/paper), heading now shows `🚀 TRADE SIGNALS` instead of `🚫 NO TRADE THIS CYCLE`. Applies to all 3 systems via shared formatter.

## Pylance f-string Fix (2026-08-16)

Fixed `claude_code_inspector_v6.py` line ~2053: extracted escape sequence to variable before f-string (Python 3.11 doesn't allow backslash in f-string expression).

## Future Annotations Cleanup (2026-09-01)

`from __future__ import annotations` was removed from all 326 Python files (no-op on Python 3.14+).
This exposed every forward reference that was previously deferred as a string.

**Fix pattern applied across the codebase:**

| Issue | Fix | Files |
|-------|-----|-------|
| Self-referencing return types (`-> ClassName`) | Quote: `-> "ClassName"` | `iv_surface.py`, `nse_fetcher.py`, `signal_backtest.py`, `holiday_calendar.py` |
| Cross-module type refs (`Optional`, `Coroutine`) | Add to `typing` / `collections.abc` imports | `supervisor.py`, `paper_executor.py` |
| Bare `collections.abc.X` usage | `import collections` | `paper_executor.py` |
| Circular import via `TYPE_CHECKING` | `if TYPE_CHECKING:` guard + quoted annotation | `backtest_stats.py` |
| Undefined names in annotations | Add explicit imports | `models_pipeline.py` (`WhatIfResult`, `StockScanResult`) |
| Pylance None narrowing (untyped SmartApi) | `isinstance(x, dict)` guard | `live_broker.py`, dashboard `ui.py` |
| Dead imports exposed by removal | Delete unused imports | 25 files, 40 imports (commit `bba7f2d`) |

**Rule for future changes:** When adding type annotations, always use quoted forward refs
(`"ClassName"`) or `TYPE_CHECKING` guards if the type isn't imported at module level.

## AngelOne Order Flow — Verified Working (2026-09-01)

End-to-end order placement on AngelOne SmartAPI verified:

1. **Auth:** TOTP-based `generateSession()` works (needs `ANGELONE_TOTP_SECRET` env var, not `TOTP_KEY`)
2. **Symbol lookup:** Instrument master at `margincalculator.angelbroking.com` — fields: `symbol` (e.g. `NIFTY08SEP2624000CE`), `token`, `strike` (in paise), `lotsize`
3. **Order placement:** `SmartConnect.placeOrder(params)` returns order ID string directly (not dict)
4. **Order book:** `SmartConnect.orderBook()` returns dict with `data` list of order objects

**Critical notes:**
- IP must be whitelisted in AngelOne SmartAPI dashboard (error `AG7002` if not)
- NIFTY lot size is **65** (not 75 — was reduced recently)
- `LiveAngelOneBroker` reads `ANGELONE_ACCESS_TOKEN` from env; data layer uses TOTP auth separately
- SmartApi stubs are untyped — always `isinstance(x, dict)` before `.get()` calls
