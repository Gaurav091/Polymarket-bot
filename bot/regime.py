"""
Regime machine — ported from poly-maker's strategy/regime.py.

Per-market state decider. When a market's price jumps suddenly (news event
already priced in by faster traders), we enter an EVENT cooloff and stop
trading that market for a period — avoids buying into a move that already
happened.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum


class Regime(Enum):
    QUIET = "quiet"        # normal — trading allowed
    EVENT = "event"        # price jump detected — cooloff, no new entries
    HALTED = "halted"      # resolved / broken data — never trade


@dataclass
class RegimeConfig:
    event_jump_ticks: float = 0.08   # 8c jump = event
    event_cooloff_s: float = 300.0    # 5 min cooloff after a jump


class MarketRegime:
    """Stateful regime tracker for one market (tracks EVENT cooloff)."""

    __slots__ = ("_event_until", "_last_price", "_cfg")

    def __init__(self, cfg: RegimeConfig | None = None):
        self._event_until = 0.0
        self._last_price: float | None = None
        self._cfg = cfg or RegimeConfig()

    def observe(self, price: float, resolved: bool = False) -> Regime:
        """Feed a new price observation; returns the current regime."""
        if resolved or price in (0.0, 1.0):
            return Regime.HALTED

        if self._last_price is not None:
            jump = abs(price - self._last_price)
            if jump >= self._cfg.event_jump_ticks:
                self._event_until = time.time() + self._cfg.event_cooloff_s
                self._last_price = price
                return Regime.EVENT

        self._last_price = price
        if time.time() < self._event_until:
            return Regime.EVENT
        return Regime.QUIET

    @property
    def cooloff_remaining(self) -> float:
        return max(0.0, self._event_until - time.time())


class RegimeTracker:
    """Tracks regimes for all tracked markets by condition_id."""

    def __init__(self):
        self._regimes: dict[str, MarketRegime] = {}

    def observe(self, condition_id: str, price: float, resolved: bool = False) -> Regime:
        if condition_id not in self._regimes:
            self._regimes[condition_id] = MarketRegime()
        return self._regimes[condition_id].observe(price, resolved)

    def can_trade(self, condition_id: str) -> bool:
        """True if market is QUIET (not in EVENT cooloff or HALTED)."""
        r = self._regimes.get(condition_id)
        if r is None:
            return True
        # Re-evaluate cooloff expiry
        if r.cooloff_remaining <= 0 and r._last_price not in (0.0, 1.0):
            return True
        return False
