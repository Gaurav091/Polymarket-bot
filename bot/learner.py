"""
Autonomous learning subsystem — reads trade history, adapts thresholds, improves performance.

Adaptive mechanisms:
  1. Threshold multipliers: tighten/loosen EDGE_THRESHOLD and MATERIALITY_THRESHOLD
     based on recent win rate per signal source (bounded [0.5×–2.0×]).
  2. Position size adjustment: reward good streaks, protect during bad streaks
     (bounded [0.5×–1.5×] on top of RiskManager's own multiplier).

Conservative mode (win_rate_20 < 0.45): thresholds × 1.2 (higher bar = stronger signals only).

All multipliers are recomputed on every trade and reset to 1.0 on restart
(no persistent state — prevents threshold drift into dangerous territory).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import config
from . import journal

log = logging.getLogger(__name__)


@dataclass
class LearnerConfig:
    """Bounds for adaptive multipliers."""
    edge_mult_min: float = 0.5
    edge_mult_max: float = 2.0
    mat_mult_min: float = 0.5
    mat_mult_max: float = 2.0
    size_mult_min: float = 0.5
    size_mult_max: float = 1.5
    min_trades_for_update: int = 3
    win_rate_calm: float = 0.65   # above this → loosen thresholds
    win_rate_warn: float = 0.50   # below this → tighten
    win_rate_critical: float = 0.45  # below this → conservative mode
    conservative_edge_boost: float = 1.2  # multiply edge_thresh in conservative mode


@dataclass
class Learner:
    """
    Reads closed trades, computes segment stats, updates adaptive multipliers.

    Usage:
        learner = Learner()
        effective_edge = learner.get_effective_edge_threshold("news")
        size_mult      = learner.get_position_size_adjustment()
        # after every close:
        learner.on_trade_closed()
    """
    cfg: LearnerConfig = field(default_factory=LearnerConfig)

    # Adaptive state (reset on restart)
    _edge_mult: float = 1.0
    _mat_mult: float = 1.0
    _size_mult: float = 1.0
    _conservative: bool = False
    # Per-source adaptive multipliers (news vs quant tracked separately)
    _source_mults: dict[str, float] = field(default_factory=dict)

    # Last computed stats (for observability)
    _last_stats: dict = field(default_factory=dict)

    # ------------------------------------------------------------
    # Public API — called from main.py
    # ------------------------------------------------------------

    def on_trade_closed(self, signal_source: str | None = None) -> None:
        """Recompute multipliers after a trade closes. Call after _close()."""
        self._update_multipliers(signal_source)

    def get_effective_edge_threshold(self, signal_source: str = "news") -> float:
        """Effective EDGE_THRESHOLD for a given signal source."""
        base = config.EDGE_THRESHOLD
        mult = self._get_source_multiplier(signal_source, "edge")
        effective = base * mult
        if self._conservative:
            effective *= self.cfg.conservative_edge_boost
        return effective

    def get_effective_materiality_threshold(self, signal_source: str = "news") -> float:
        """Effective MATERIALITY_THRESHOLD for a given signal source."""
        base = config.MATERIALITY_THRESHOLD
        mult = self._get_source_multiplier(signal_source, "mat")
        return base * mult

    def get_position_size_adjustment(self) -> float:
        """Multiplier [0.5–1.5] applied on top of RiskManager.position_size_multiplier."""
        return self._size_mult

    def is_conservative(self) -> bool:
        return self._conservative

    def summary(self) -> dict:
        """Current adaptive state for logging/debugging."""
        return {
            "edge_mult": round(self._edge_mult, 3),
            "mat_mult": round(self._mat_mult, 3),
            "size_mult": round(self._size_mult, 3),
            "conservative": self._conservative,
            "last_stats": self._last_stats,
        }

    # ------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------

    def _get_source_multiplier(self, signal_source: str, _kind: str) -> float:
        """Source-specific multiplier based on per-source win rate.

        News (85% WR): relaxed thresholds (0.8x) to fire more often.
        Quant (35% WR): tighter thresholds (1.3x) to filter noise.
        Unknown: use global multiplier.
        """
        if signal_source in self._source_mults:
            return self._source_mults[signal_source]
        return self._edge_mult

    def _update_multipliers(self, signal_source: str | None = None) -> None:
        """Compute segment stats and update adaptive multipliers."""
        # Global stats
        seg = journal.get_segment_stats(signal_source=signal_source, min_trades=self.cfg.min_trades_for_update)
        self._last_stats = seg

        if seg["count"] < self.cfg.min_trades_for_update:
            return

        wr = seg["win_rate"]

        # Conservative mode: win_rate_20 < 0.45
        self._conservative = wr < self.cfg.win_rate_critical

        if self._conservative:
            # Lock down: take only very high confidence signals
            self._edge_mult = max(self.cfg.edge_mult_min, 0.85)
            self._mat_mult = max(self.cfg.mat_mult_min, 0.85)
            self._size_mult = max(self.cfg.size_mult_min, 0.6)
            log.warning(f"[learner] CONSERVATIVE mode — win_rate={wr:.1%} (<45%)")
            return

        # Normal mode — adjust based on win rate
        if wr < self.cfg.win_rate_warn:
            # Bad patch — tighten
            self._edge_mult = max(self.cfg.edge_mult_min, self._edge_mult * 0.90)
            self._mat_mult = max(self.cfg.mat_mult_min, self._mat_mult * 0.90)
            self._size_mult = max(self.cfg.size_mult_min, self._size_mult * 0.85)
        elif wr >= self.cfg.win_rate_calm:
            # Good patch — loosen cautiously
            self._edge_mult = min(self.cfg.edge_mult_max, self._edge_mult * 1.05)
            self._mat_mult = min(self.cfg.mat_mult_max, self._mat_mult * 1.05)
            self._size_mult = min(self.cfg.size_mult_max, self._size_mult * 1.10)
        # else: hold

        log.debug(
            f"[learner] win_rate={wr:.1%} → "
            f"edge_mult={self._edge_mult:.2f} mat_mult={self._mat_mult:.2f} "
            f"size_mult={self._size_mult:.2f}"
        )

        # Per-source adaptive: news (85% WR) gets relaxed, quant (35% WR) gets tight
        for src in ("news", "python-quant"):
            src_seg = journal.get_segment_stats(signal_source=src, min_trades=3)
            if src_seg["count"] < 3 or src_seg["win_rate"] is None:
                continue
            src_wr = src_seg["win_rate"]
            if src_wr >= 0.60:
                # Profitable source: relax thresholds (0.8x = lower bar)
                self._source_mults[src] = max(0.5, self._source_mults.get(src, 1.0) * 0.95)
            elif src_wr < 0.40:
                # Losing source: tighten thresholds (1.3x = higher bar)
                self._source_mults[src] = min(2.0, self._source_mults.get(src, 1.0) * 1.05)
            log.debug(f"[learner] {src}: WR={src_wr:.0%} → mult={self._source_mults.get(src, 1.0):.2f}")
