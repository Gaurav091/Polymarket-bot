"""
TimesFM 2.5 (200M) forecaster — Google's time-series foundation model.

Adds a 4th signal family to the quant ensemble: foundation-model price-path
forecasting. Uses the Apache-2.0 licensed 200M checkpoint (NOT TimesFM 3.0,
whose weights are non-commercial-only — unusable for a real-money bot).

Design constraints (this machine):
- CPU-only (Intel UHD 620, no CUDA) → ~0.7s/market batched, 13s single
- Model load takes ~20-40s → lazy singleton, loaded once per process
- Forecasts cached 15 min per token — prices move slowly at hourly fidelity
- Batched per scan cycle: all markets forecast in ONE forward pass

Signal semantics (matches the other ensemble members):
    score in [-1, +1]
    +1 = YES more likely (price forecast rises)
    -1 = NO more likely (price forecast falls)

The raw drift is scaled: a forecast of +5% on a 0.10 market is a strong
signal; +5% on a 0.90 market is noise. Drift is normalized by price and
capped at ±1.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import numpy as np

from . import config

log = logging.getLogger(__name__)

# ============================================================
# Lazy singleton — torch import + checkpoint load is 20-40s
# ============================================================
_MODEL = None
_MODEL_LOCK = threading.Lock()
_LOAD_ATTEMPTED = False


def _get_model():
    """Load TimesFM once per process. Returns None on any failure —
    the ensemble must keep working without this signal."""
    global _MODEL, _LOAD_ATTEMPTED
    if _MODEL is not None:
        return _MODEL
    with _MODEL_LOCK:
        if _LOAD_ATTEMPTED:  # failed before — don't retry every scan
            return None
        _LOAD_ATTEMPTED = True
        try:
            from timesfm.configs import ForecastConfig
            from timesfm.timesfm_2p5 import timesfm_2p5_torch as t

            t0 = time.time()
            tfm = t.TimesFM_2p5_200M_torch.from_pretrained(
                "google/timesfm-2.5-200m-pytorch"
            )
            cfg = ForecastConfig(
                max_context=512,          # hourly candles → ~3 weeks
                max_horizon=16,           # up to 16h ahead
                normalize_inputs=True,
                window_size=0,
                per_core_batch_size=8,    # CPU batching
                use_continuous_quantile_head=False,
                force_flip_invariance=True,
                infer_is_positive=True,
                fix_quantile_crossing=True,
            )
            tfm.compile(forecast_config=cfg, device="cpu")
            _MODEL = tfm
            log.info(f"[timesfm] model ready in {time.time()-t0:.1f}s (CPU, 200M)")
            return _MODEL
        except Exception as e:
            log.warning(f"[timesfm] unavailable — ensemble continues without it: {e}")
            return None


# ============================================================
# Forecast cache — token_id → (ts, drift_score)
# ============================================================
@dataclass
class _FCacheEntry:
    ts: float
    score: float
    horizon_mean: float


_fcache: dict[str, _FCacheEntry] = {}
_FCACHE_TTL = 900.0  # 15 min — hourly candles don't move faster


def forecast_drift(token_id: str, price_history: list[float]) -> float | None:
    """Forecast next N hours; return drift score in [-1, +1] or None.

    Caller supplies the price history (already fetched by the ensemble)
    so we never fetch twice.
    """
    if not config.TIMESFM_ENABLED:
        return None
    if len(price_history) < config.TIMESFM_MIN_HISTORY:
        return None

    cached = _fcache.get(token_id)
    if cached and time.time() - cached.ts < _FCACHE_TTL:
        return cached.score

    model = _get_model()
    if model is None:
        return None

    try:
        series = np.asarray(price_history, dtype=np.float32)
        t0 = time.time()
        points, _quantiles = model.forecast(
            horizon=config.TIMESFM_HORIZON, inputs=[series]
        )
        elapsed = time.time() - t0
        fc = np.asarray(points[0], dtype=float)
        last = float(series[-1])
        fc_mean = float(fc.mean())

        # Drift normalized by price, capped ±1
        drift = (fc_mean - last) / max(last, 0.02)
        score = max(-1.0, min(1.0, drift * config.TIMESFM_DRIFT_SCALE))

        _fcache[token_id] = _FCacheEntry(
            ts=time.time(), score=score, horizon_mean=fc_mean
        )
        log.debug(
            f"[timesfm] {token_id[:10]} fc={fc_mean:.3f} last={last:.3f} "
            f"score={score:+.2f} ({elapsed:.1f}s)"
        )
        return score
    except Exception as e:
        log.debug(f"[timesfm] forecast failed {token_id[:10]}: {e}")
        return None


def forecast_batch(markets_hist: dict[str, list[float]]) -> dict[str, float]:
    """Batched forecast: {token_id: price_history} → {token_id: score}.

    One forward pass for all markets — 0.7s/market vs 13s single.
    Use this in the scan loop, not forecast_drift per market.
    """
    if not config.TIMESFM_ENABLED:
        return {}
    # Filter: enough history, not cached
    todo = {}
    results: dict[str, float] = {}
    now = time.time()
    for token_id, hist in markets_hist.items():
        if len(hist) < config.TIMESFM_MIN_HISTORY:
            continue
        cached = _fcache.get(token_id)
        if cached and now - cached.ts < _FCACHE_TTL:
            results[token_id] = cached.score
        else:
            todo[token_id] = hist
    if not todo:
        return results

    model = _get_model()
    if model is None:
        return results

    try:
        series_list = [np.asarray(h, dtype=np.float32) for h in todo.values()]
        t0 = time.time()
        points, _q = model.forecast(
            horizon=config.TIMESFM_HORIZON, inputs=series_list
        )
        elapsed = time.time() - t0
        for (token_id, hist), pt in zip(todo.items(), points):
            fc = np.asarray(pt, dtype=float)
            last = float(hist[-1])
            fc_mean = float(fc.mean())
            drift = (fc_mean - last) / max(last, 0.02)
            score = max(-1.0, min(1.0, drift * config.TIMESFM_DRIFT_SCALE))
            _fcache[token_id] = _FCacheEntry(
                ts=time.time(), score=score, horizon_mean=fc_mean
            )
            results[token_id] = score
        log.info(
            f"[timesfm] batch: {len(todo)} markets in {elapsed:.1f}s "
            f"({elapsed/max(len(todo),1):.2f}s/mkt)"
        )
    except Exception as e:
        log.warning(f"[timesfm] batch failed: {e}")
    return results


def is_available() -> bool:
    """True if the model loaded successfully (for selfcheck)."""
    return _get_model() is not None
