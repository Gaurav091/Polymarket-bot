# Polymarket Survival Bot

A Polymarket trading bot that **must earn money to stay alive**. If it realizes no profit within a 30-minute window, it dies — halts permanently and writes a death report. Every profitable trade resets the clock.

Built by combining the best of 8 reference repos:

| Borrowed from | Feature |
|---|---|
| [PolyAgent](https://github.com/omkute101/PolyAgent) | Event-driven pipeline: news → match → classify → edge → trade; niche-market focus; quarter-Kelly sizing; SQLite journal |
| [Polymarket-bot](https://github.com/MrFadiAi/Polymarket-bot) | 4-layer risk management (daily/monthly/drawdown/total-loss halt); dynamic position sizing; CLOB minimum-order enforcement |
| [poly-maker](https://github.com/warproxxx/poly-maker) | Regime machine (EVENT cooloff on price jumps); error-rate circuit breaker |
| [prediction-market-analysis](https://github.com/Jon-Becker/prediction-market-analysis) | Favorite-longshot bias calibration; market-resolution detection; empirical calibration lookup table |
| [Polymarket/agents](https://github.com/Polymarket/agents) | Classification prompt design (direction + materiality, not probability) |
| [poly_data](https://github.com/example/poly_data) | On-chain trade flow signal (whale detection, smart money) |
| Custom | WebSocket real-time price watcher; calibration accuracy tracking |

## How survival mode works

```
BOOT (grace period)
  ↓ clock arms
ALIVE ──profitable trade──→ clock resets (30:00)
  │                              ↑
  │ no profit as window drains    │
  ↓                              │
CRITICAL (<25% of window left)   │
  ↓ still no profit              │
DEAD — permanent halt, death report written to DB
```

- **Only realized profit keeps it alive.** Losses do NOT reset the clock.
- `SURVIVAL_WINDOW_MINUTES` (default 30) — the death window
- `SURVIVAL_GRACE_MINUTES` (default 10) — startup grace before the clock arms
- `SURVIVAL_ENABLED=false` disables the mechanic for testing

## Pipeline (every cycle)

1. **Survival heartbeat** — die if the window elapsed without profit
2. **Risk check** — 4-layer gates (5% daily / 15% monthly / 25% drawdown / 40% total halt)
3. **API circuit breaker** — ≥50% API error rate halts entries (stale-data protection)
4. **Market refresh** — Gamma API, paginated, niche filter ($1K–$500K volume, 5–95c price), **spread filter** (reject >8¢ spread)
5. **Calibration check** — poll resolved markets, update accuracy stats (every 5 min)
6. **News poll** — RSS feeds (Google News, TechCrunch, Ars Technica, The Verge)
7. **Match** — keyword-overlap scoring headlines → markets
8. **Classify** — LLM (any provider via litellm) or keyword fallback; direction + materiality
9. **Edge** — calibration-adjusted price (empirical lookup table) vs classification; quarter-Kelly sizing
10. **Regime gate** — skip markets in EVENT cooloff (price already jumped)
11. **Execute** — paper mode by default; live via `py-clob-client` when `DRY_RUN=false`; **log calibration prediction**
12. **Quant scan** — 5-signal ensemble: momentum, mean-reversion, order-book flow, **on-chain flow** (whale detection), TimesFM
13. **Monitor** — take-profit +12c / stop-loss −35c (capped 2–6c) / timeout; realized profit feeds the survival clock
14. **WebSocket watcher** — background thread, real-time price updates with momentum tracking

## Setup

```powershell
# venv already created with uv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt

# configure
Copy-Item .env.example .env   # then edit

# run (paper mode — safe)
.venv\Scripts\python.exe -m bot.main
```

## Configuration (.env)

| Variable | Default | Purpose |
|---|---|---|
| `SURVIVAL_WINDOW_MINUTES` | 30 | Death window |
| `SURVIVAL_GRACE_MINUTES` | 10 | Startup grace |
| `DRY_RUN` | true | `false` = real money via CLOB |
| `CAPITAL_USD` | 100 | Risk budget for sizing + limits |
| `MAX_BET_USD` / `MIN_BET_USD` | 10 / 1 | Per-trade size clamp |
| `EDGE_THRESHOLD` | 0.10 | Minimum edge to trade |
| `MIN_VOLUME_USD` / `MAX_VOLUME_USD` | 1K / 500K | Niche-market filter |
| `MATERIALITY_THRESHOLD` | 0.6 | Min LLM materiality to trade |
| `DAILY_MAX_LOSS_PCT` etc. | .05/.15/.25/.40 | 4-layer risk limits |
| `ANTHROPIC_API_KEY` etc. | — | Any LLM key enables LLM classification |

## Self-checks

```powershell
.venv\Scripts\python.exe selfcheck.py
```

18 assertions covering: survival lifecycle (boot→alive→critical→death), profit-resets-clock, loss-doesn't, journal PnL round-trip, sizing clamps, regime machine, calibration, NO-side PnL, tick rounding, token_id fallback, min-profit gate, py-clob-client API, quant math, live quant signal, weighted lexicon, TimesFM forecast.

## Data

- `data/trades.db` — SQLite journal: trades, survival events, peak equity, calibration predictions
- Death reports: `survival_events` table, `event='death'`
- Calibration accuracy: `calibration_log` table (signal predictions vs actual outcomes)

## Live trading

1. Set `DRY_RUN=false`
2. Add `POLYMARKET_PRIVATE_KEY` (funded wallet, USDC on Polygon)
3. `uv pip install --python .venv\Scripts\python.exe py-clob-client`
4. Start small: `CAPITAL_USD=50`, `MAX_BET_USD=5`

**Warning:** untested strategy = hypothesis. Run paper mode first; the survival mechanic will kill the bot quickly if the edge isn't real — that's the point.
