# Agent System — Active Task State

## Current Phase: Agent System Enhancement (Deduplication + Progressive Disclosure)
**Date:** 2026-09-01
**Status:** Agent boilerplate deduplicated, Verification sections added, frontmatter metadata added, .claude mirrors synced

## Completed Work
- [x] **Deduplicated Truth Protocol** from all 16 `.github/agents/*.agent.md` files
  - Replaced 30-line inline block with 1-line reference to `.github/copilot-instructions.md` §Truth Protocol
  - ~480 lines saved
- [x] **Deduplicated Loop-Engineering** from 15 agent files
  - Replaced 103-line inline block with reference to `.github/copilot-instructions.md` §loop-engineering
  - ~1,455 lines saved (fable-orchestrator kept its unique detailed spec)
- [x] **Added Verification sections** to 4 trading agents (CEO, Quant, Risk, Execution)
  - Pattern: When to Use → Prerequisites → Workflow → Verification (from cybersecurity skill pattern)
  - Each has a checklist forcing evidence-based output
- [x] **Added frontmatter metadata** for progressive discovery
  - `tier` (critical/specialist/standard), `category` (trading-domain/fable-techniques/model-routing), `cost-tier`, `dependencies`
  - Enables ~30-token scanning for agent selection (cybersecurity pattern)
- [x] **Synced `.claude/agents/` mirrors** from `.github/agents/` sources
  - 16 files copied + `.fix_agents.py` normalization (tools/models for Claude CLI)
  - Content drift eliminated

## Total Impact
- `.github/agents/`: ~4,400 → 2,706 lines (~39% reduction)
- `.claude/agents/`: fully synced, no drift
- All 16 files in both locations have valid YAML frontmatter (verified)

## Next Actions
1. Commit and push changes to `main`
2. Consider adding `added_date`/`last_verified` decay metadata to `auto_lessons.md` (agentmemory pattern)
3. Consider moving hardcoded API key from `.claude/settings.json` to env var

## Delegation Log
- Fable Orchestrator: Deduplicated boilerplate, added Verification sections, synced mirrors
- Explore subagent: Inventoried agent system, mapped external patterns to internal gaps
## Turn Log: 2026-08-24 — Momentum zero-trade fixes
**Task:** Diagnose + fix intraday momentum zero-trade day (index + stocks).
**Root causes fixed:** (1) regime attr bug in scan_enrich.py — getattr(sig,'regime') never existed, all signals forced Range treatment; replaced with _signal_regime() reading sig.market_regime at 4 sites. (2) MIN_RR=1.5 unreachable vs cost-adjusted TP2 R:R — added min_rr param to SignalQualityGate.check/check_raw; momentum callers pass 1.0. (3) ENRICHED log printed stale sig.score → now result.score.
**Verification:** py_compile OK; functional sim OK (UPTREND 44 vs RANGE 32 pts; rr=1.31 passes min_rr=1.0, default still rejects); pytest tests/unit 1403 passed.
**Pending:** Restart the 3 trader processes to load new code (restart rule). RSI>75 overbought block left unchanged (by design).
