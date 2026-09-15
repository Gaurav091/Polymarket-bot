# Loop Engineering Skill

**Purpose**: Enable agents to run persistent, self-completing task loops with scheduling, checkpointing, quality gates, and auto-recovery.

## When to Use
- Any task that needs to run repeatedly (cron, continuous monitoring, pipelines)
- Long-running tasks that may be interrupted and need recovery
- Multi-phase tasks requiring quality gates between phases
- Tasks needing cost tracking and model tier auto-scaling

## Core Primitives

### 1. loop-schedule — Register Recurring Tasks
```bash
python scripts/ops/loop_schedule.py register \
  --pattern trading-signal-gen \
  --cron "*/5 9-15 * * 1-5" \
  --script "starters/trading-signal-gen/run_signal_gen.py" \
  --level L1
```

### 2. loop-gate — Quality Gates with Auto-Retry
```bash
# In agent workflow:
python scripts/ops/loop_gate.py --phase "signal-generation" \
  --criteria "score>=70,no_conflicts,risk_approved" \
  --retry 3 --backoff 30
# Returns: PASS / FAIL / RETRY
```

### 3. loop-sync — State Synchronization
```bash
# Push artifacts to shared state
python scripts/ops/loop_sync.py --push --file "signals.json" --pattern trading-signal-gen

# Pull latest state
python scripts/ops/loop_sync.py --pull --pattern trading-signal-gen
```

### 4. loop-cost — Cost Tracking & Tier Auto-Scaling
```bash
# Track iteration cost
python scripts/ops/loop_cost.py --track --model o3 --tokens 45000 --pattern trading-signal-gen

# Check if should downgrade
python scripts/ops/loop_cost.py --check --threshold 0.50 --pattern trading-signal-gen
# Returns: OK / DOWNGRADE
```

### 5. loop-audit — Loop Ready Scoring
```bash
# Score a pattern's loop readiness (0-100)
python scripts/ops/loop_audit.py --pattern trading-signal-gen --score
# Checks: idempotency, checkpointing, gates, observability, rollback, cost-tracking
```

### 6. checkpoint — WIP State Persistence
```bash
# Save checkpoint
python scripts/ops/checkpoint_wip.py "trading-signal-gen: phase 3 complete, 47 signals generated"

# Restore latest
python scripts/ops/checkpoint_wip.py --restore
```

## Agent Integration Patterns

### For @fable-orchestrator (Loop Controller)
```python
# 1. Load pattern config
pattern = load_yaml("patterns/registry.yaml")["trading-signal-gen"]

# 2. Read loop state
context = read_file(".github/agents/CONTEXT.md")

# 3. Execute phase with gate
result = run_phase(pattern, context.current_phase)
gate = run_loop_gate(pattern.current_phase, result)

# 4. On PASS: checkpoint, advance phase
if gate == "PASS":
    checkpoint(f"{pattern.id}: phase {phase} complete")
    advance_phase()
# 5. On FAIL: retry (max 3), then escalate
```

### For @deep / @standard (Loop Workers)
```python
# At start of each loop iteration:
context = read_file(".github/agents/CONTEXT.md")
checkpoint(f"worker: starting {task_id}")

# After each major step:
gate = run_loop_gate(step_name, output)
if gate != "PASS":
    retry_with_backoff(max=3)

# At end:
checkpoint(f"worker: completed {task_id}")
```

### For @router (Loop-Aware Routing)
```python
# Detect loop tasks by keywords:
loop_keywords = ["daily", "continuous", "monitor", "pipeline", "scheduled", "recurring", "cron"]
if any(k in task.lower() for k in loop_keywords):
    route_to("@fable-orchestrator", pattern_id=detect_pattern(task))
```

## Phased Rollout Levels

| Level | Name | Human Gates | Auto-Retry | Self-Heal | Use Case |
|-------|------|-------------|------------|-----------|----------|
| **L1** | Report Only | All decisions | No | No | Week 1 validation |
| **L2** | Assisted | Critical only | Yes (3x) | No | Week 2-3 |
| **L3** | Unattended | Circuit breakers | Yes (3x) | Yes | Week 4+ |

Current level per pattern: `patterns/registry.yaml` → `week_one_mode: true/false`

## Loop Completion Protocol

A loop iteration is **complete** only when:
- [ ] All todo items for the iteration are `completed`
- [ ] All quality gates for the iteration return `PASS`
- [ ] Checkpoint written with iteration summary
- [ ] Cost logged via `loop-cost`
- [ ] Next iteration scheduled (if recurring)

## Error Handling in Loops

| Error Type | Action |
|------------|--------|
| Transient (network, rate limit) | Auto-retry with exponential backoff (max 3) |
| Validation failure (gate FAIL) | Retry with adjusted params (max 3), then escalate |
| Context overflow | Summarize, delegate to fresh subagent via `loop-sync` |
| Hard failure (exception) | Checkpoint, log, escalate to human (L1/L2) or circuit breaker (L3) |
| Interruption (crash, kill) | On restart: read CONTEXT.md, restore from last checkpoint |

## Files Created by This Skill

| File | Purpose |
|------|---------|
| `scripts/ops/loop_schedule.py` | Cron registration & management |
| `scripts/ops/loop_gate.py` | Quality gates with retry logic |
| `scripts/ops/loop_sync.py` | Cross-agent state sync |
| `scripts/ops/loop_cost.py` | Token/cost tracking & tier scaling |
| `scripts/ops/loop_audit.py` | Loop Ready scoring (0-100) |
| `patterns/registry.yaml` | Pattern definitions (source of truth) |
| `.github/agents/CONTEXT.md` | Loop state (single writer) |

## Quick Reference for Agents

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