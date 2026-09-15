"""
Survival Mode — the heartbeat of the bot.

The bot must earn money to stay alive. If no realized profit occurs within
SURVIVAL_WINDOW_MINUTES, the bot dies: it halts trading, writes a death
report, and exits. Every realized profitable trade resets the clock.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from . import config


class VitalState(Enum):
    BOOT = "boot"            # grace period, clock not ticking yet
    ALIVE = "alive"          # clock ticking, must earn within window
    CRITICAL = "critical"    # less than 25% of window remains
    DEAD = "dead"            # failed to earn in time — permanent halt


@dataclass
class SurvivalStatus:
    state: VitalState = VitalState.BOOT
    window_minutes: int = config.SURVIVAL_WINDOW_MINUTES
    last_profit_ts: Optional[float] = None   # unix ts of last realized profit
    started_ts: float = field(default_factory=time.time)
    total_realized_profit: float = 0.0
    total_realized_loss: float = 0.0
    deaths: int = 0

    @property
    def seconds_remaining(self) -> float:
        """Seconds left before death (inf during boot grace)."""
        if self.state == VitalState.BOOT:
            grace_end = self.started_ts + config.SURVIVAL_GRACE_MINUTES * 60
            remaining = grace_end - time.time()
            return remaining if remaining > 0 else 0.0
        if self.state == VitalState.DEAD or self.last_profit_ts is None:
            return 0.0
        deadline = self.last_profit_ts + self.window_minutes * 60
        return max(0.0, deadline - time.time())

    @property
    def time_since_profit(self) -> float:
        if self.last_profit_ts is None:
            return time.time() - self.started_ts
        return time.time() - self.last_profit_ts


class SurvivalMonitor:
    """
    Tracks realized profit timing. The bot stays alive only by continuously
    earning. Call `record_profit()` on every realized profitable trade.
    """

    def __init__(self, on_death: Optional[Callable[["SurvivalStatus"], None]] = None):
        self.status = SurvivalStatus(window_minutes=config.SURVIVAL_WINDOW_MINUTES)
        self._on_death = on_death
        self._death_reported = False

    # ------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------
    def arm(self) -> None:
        """End of grace period — the survival clock starts now."""
        if self.status.state == VitalState.BOOT:
            self.status.state = VitalState.ALIVE
            self.status.last_profit_ts = time.time()

    def record_profit(self, amount_usd: float) -> None:
        """A profitable trade was realized — resets the death clock.
        Only counts if it meets the minimum profit threshold."""
        if amount_usd < config.SURVIVAL_MIN_PROFIT_USD:
            return
        self.status.total_realized_profit += amount_usd
        self.status.last_profit_ts = time.time()
        if self.status.state in (VitalState.ALIVE, VitalState.CRITICAL):
            self.status.state = VitalState.ALIVE

    def record_loss(self, amount_usd: float) -> None:
        """A losing trade was realized. Does NOT reset the clock —
        only earning money keeps the bot alive."""
        if amount_usd <= 0:
            return
        self.status.total_realized_loss += amount_usd

    def is_critical(self) -> bool:
        """True when < CRITICAL_WINDOW_MINUTES remain and bot is alive/critical."""
        if not config.SURVIVAL_ENABLED:
            return False
        if not config.SURVIVAL_EMERGENCY_ENABLED:
            return False
        if self.status.state not in (VitalState.ALIVE, VitalState.CRITICAL):
            return False
        return self.status.seconds_remaining < config.CRITICAL_WINDOW_MINUTES * 60

    # ------------------------------------------------------------
    # Heartbeat — call every loop iteration
    # ------------------------------------------------------------
    def check(self) -> VitalState:
        if not config.SURVIVAL_ENABLED:
            # Survival disabled — bot runs forever, never dies.
            if self.status.state == VitalState.BOOT:
                self.status.state = VitalState.ALIVE
                self.status.last_profit_ts = time.time()
            return self.status.state

        if self.status.state == VitalState.BOOT:
            if time.time() - self.status.started_ts >= config.SURVIVAL_GRACE_MINUTES * 60:
                self.arm()
            return self.status.state

        if self.status.state == VitalState.DEAD:
            return VitalState.DEAD

        remaining = self.status.seconds_remaining
        window_seconds = self.status.window_minutes * 60

        if remaining <= 0:
            self._die()
            return VitalState.DEAD

        if remaining < window_seconds * 0.25:
            self.status.state = VitalState.CRITICAL
        else:
            self.status.state = VitalState.ALIVE

        return self.status.state

    def _die(self) -> None:
        if self._death_reported:
            return
        self._death_reported = True
        self.status.state = VitalState.DEAD
        self.status.deaths += 1
        if self._on_death:
            try:
                self._on_death(self.status)
            except Exception:
                pass

    # ------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------
    def summary(self) -> str:
        s = self.status
        if not config.SURVIVAL_ENABLED:
            return (
                f"[RUN] survival mode OFF — running indefinitely | "
                f"earned ${s.total_realized_profit:.2f} | "
                f"lost ${s.total_realized_loss:.2f}"
            )
        if s.state == VitalState.BOOT:
            return (
                f"[BOOT] grace period — {self._fmt(s.seconds_remaining)} until "
                f"survival clock arms (window: {s.window_minutes}m)"
            )
        if s.state == VitalState.DEAD:
            return (
                f"[DEAD] survived {self._fmt(s.time_since_profit)} without profit. "
                f"Halting permanently."
            )
        emoji = "🟢" if s.state == VitalState.ALIVE else "🔴"
        return (
            f"{emoji} [{s.state.value.upper()}] "
            f"{self._fmt(s.seconds_remaining)} to earn or die | "
            f"earned ${s.total_realized_profit:.2f} | "
            f"lost ${s.total_realized_loss:.2f}"
        )

    @staticmethod
    def _fmt(seconds: float) -> str:
        m, s = divmod(max(0, int(seconds)), 60)
        return f"{m:02d}:{s:02d}"
