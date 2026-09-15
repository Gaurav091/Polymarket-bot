"""
Calibration — favorite-longshot bias correction.

Two methods:
1. Empirical lookup table (from prediction-market-analysis): bucket-level
   win rates from thousands of resolved markets. Data-driven adjustment.
2. Simple linear shading (fallback): when the lookup table is unavailable.

The lookup table is preferred when available — it captures non-linear
mispricing patterns that linear shading misses.
"""
from __future__ import annotations

from .calibration_table import (
    adjusted_probability,
    compute_edge_boost,
    get_confidence,
    lookup_adjustment,
)


def calibrated_probability(raw_price: float) -> float:
    """
    Apply calibration correction to a market price.
    
    Uses the empirical lookup table for data-driven adjustment.
    Falls back to simple linear shading if lookup fails.
    
    Returns: adjusted probability in [0.01, 0.99]
    """
    try:
        return adjusted_probability(raw_price)
    except Exception:
        pass
    # Fallback: simple linear shading
    if raw_price >= 0.8:
        overshoot = (raw_price - 0.8) / 0.2
        return raw_price - 0.03 * overshoot
    if raw_price <= 0.2:
        undershoot = (0.2 - raw_price) / 0.2
        return raw_price + 0.02 * undershoot
    return raw_price


def is_resolved(yes_price: float, no_price: float | None = None) -> bool:
    """Detect a resolved market: one side > 0.99, other < 0.01.
    (Same heuristic used in prediction-market-analysis's win-rate analyses.)"""
    if no_price is None:
        no_price = 1.0 - yes_price
    return (yes_price > 0.99 and no_price < 0.01) or (yes_price < 0.01 and no_price > 0.99)
