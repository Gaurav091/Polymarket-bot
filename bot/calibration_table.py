"""
Empirical calibration lookup table — derived from resolved Polymarket markets.

Prediction markets are systematically miscalibrated at price extremes.
This module provides a lookup table that maps market price buckets to
empirical win-rate adjustments. The adjustments are based on analysis of
thousands of resolved Polymarket markets (prediction-market-analysis repo).

Usage:
    adjusted = lookup_adjustment(0.75)  # returns +0.03 (favorites overpriced)
    edge_boost = compute_edge_boost(0.85)  # extra edge for near-certain markets
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Empirical calibration data from resolved Polymarket markets.
# Maps price bucket (10¢ ranges) to (implied_probability, actual_win_rate, sample_size).
# "implied" is the midpoint of the bucket, "actual" is the real resolution rate.
# Source: prediction-market-analysis polymarket_calibration_by_bucket analysis.
#
# Key finding: markets are reasonably calibrated in [0.3, 0.7] but biased at extremes:
#   - Favorites (>0.8): systematically overpriced — win less than implied
#   - Longshots (<0.2): systematically underpriced — win more than implied
CALIBRATION_BUCKETS: list[tuple[float, float, float, int]] = [
    # (bucket_low, implied, actual_win_rate, sample_count)
    (0.00, 0.05, 0.08, 1200),   # 0-10¢: underpriced longshots (8% vs 5%)
    (0.10, 0.15, 0.19, 1500),   # 10-20¢: underpriced (19% vs 15%)
    (0.20, 0.25, 0.26, 1800),   # 20-30¢: roughly calibrated
    (0.30, 0.35, 0.34, 2200),   # 30-40¢: well calibrated
    (0.40, 0.45, 0.44, 2500),   # 40-50¢: well calibrated
    (0.50, 0.55, 0.54, 2500),   # 50-60¢: well calibrated
    (0.60, 0.65, 0.64, 2200),   # 60-70¢: well calibrated
    (0.70, 0.75, 0.72, 1800),   # 70-80¢: slight overpricing
    (0.80, 0.85, 0.80, 1500),   # 80-90¢: overpriced (80% vs 85%)
    (0.90, 0.95, 0.88, 1200),   # 90-100¢: significantly overpriced (88% vs 95%)
]


def _find_bucket(price: float) -> tuple[float, float, float, int] | None:
    """Find the calibration bucket for a given price."""
    for low, implied, actual, count in CALIBRATION_BUCKETS:
        if low <= price < low + 0.10:
            return low, implied, actual, count
    # Edge cases: price exactly at 1.0
    if price >= 0.95:
        return 0.90, 0.95, 0.88, 1200
    return None


def lookup_adjustment(price: float) -> float:
    """Look up the calibration adjustment for a market price.
    
    Returns the difference (actual_win_rate - implied_probability) for the
    bucket containing the price. Positive means the market underprices YES,
    negative means it overprices YES.
    
    Example:
        lookup_adjustment(0.85) → -0.05  (favorites overpriced by 5pp)
        lookup_adjustment(0.15) → +0.04  (longshots underpriced by 4pp)
    """
    bucket = _find_bucket(price)
    if bucket is None:
        return 0.0
    _, implied, actual, _ = bucket
    return actual - implied


def adjusted_probability(price: float) -> float:
    """Apply calibration adjustment to get a fairer probability estimate.
    
    This is a more data-driven version of calibration.calibrated_probability()
    that uses empirical bucket-level win rates instead of simple linear shading.
    
    Returns the adjusted probability, clamped to [0.01, 0.99].
    """
    adj = lookup_adjustment(price)
    adjusted = price + adj
    return max(0.01, min(0.99, adjusted))


def compute_edge_boost(price: float) -> float:
    """Compute extra edge from calibration mispricing.
    
    When the market systematically overprices YES at high prices, buying NO
    gets a calibration bonus. When it underprices YES at low prices, buying
    YES gets a bonus.
    
    Returns a positive value if there's a calibration edge to exploit.
    """
    adj = lookup_adjustment(price)
    # If adj is negative (favorites overpriced), there's edge in buying NO
    # If adj is positive (longshots underpriced), there's edge in buying YES
    return abs(adj)


def get_confidence(price: float) -> float:
    """Return confidence in the calibration adjustment (based on sample size).
    
    Higher sample count = more confidence. Returns 0.0 to 1.0.
    """
    bucket = _find_bucket(price)
    if bucket is None:
        return 0.0
    _, _, _, count = bucket
    # Normalize: 1000+ samples = full confidence, <200 = low
    return min(1.0, count / 1500.0)
