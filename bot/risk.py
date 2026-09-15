"""
4-layer risk management — ported from Polymarket-bot's professional system.

Layers:
1. Daily loss limit (default 5%)
2. Monthly loss limit (default 15%)
3. Max drawdown from peak (default 25%)
4. Total loss halt (default 40% — permanent halt)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from . import config
from . import journal
from . import journal_stats


@dataclass
class RiskState:
    peak_equity: float = config.CAPITAL_USD
    halted: bool = False
    halt_reason: str = ""


class RiskManager:
    def __init__(self):
        self.state = RiskState()
        self._load_peak_from_db()

    def _load_peak_from_db(self):
        try:
            peak = journal.get_peak_equity()
            if peak is not None and peak > self.state.peak_equity:
                self.state.peak_equity = peak
        except Exception:
            pass

    def check(self, current_equity: float) -> tuple[bool, str]:
        """Returns (allowed_to_trade, reason). Updates halt state."""
        if self.state.halted:
            return False, self.state.halt_reason

        # Track peak equity for drawdown
        if current_equity > self.state.peak_equity:
            self.state.peak_equity = current_equity
            journal.save_peak_equity(self.state.peak_equity)

        capital = config.CAPITAL_USD
        pnl_pct = (current_equity - capital) / capital

        # Layer 4: total loss halt (permanent)
        if pnl_pct <= -config.TOTAL_MAX_LOSS_PCT:
            self.state.halted = True
            self.state.halt_reason = (
                f"TOTAL LOSS HALT: {pnl_pct:.1%} exceeds {config.TOTAL_MAX_LOSS_PCT:.0%}"
            )
            return False, self.state.halt_reason

        # Layer 3: drawdown from peak
        drawdown = (self.state.peak_equity - current_equity) / self.state.peak_equity
        if drawdown >= config.MAX_DRAWDOWN_PCT:
            self.state.halted = True
            self.state.halt_reason = (
                f"DRAWDOWN HALT: {drawdown:.1%} from peak exceeds "
                f"{config.MAX_DRAWDOWN_PCT:.0%}"
            )
            return False, self.state.halt_reason

        # Layer 2: monthly loss limit
        month_pnl = journal_stats.get_month_pnl()
        if month_pnl <= -capital * config.MONTHLY_MAX_LOSS_PCT:
            return False, (
                f"MONTHLY LOSS LIMIT: ${month_pnl:.2f} exceeds "
                f"-{capital * config.MONTHLY_MAX_LOSS_PCT:.2f}"
            )

        # Layer 1: daily loss limit
        day_pnl = journal_stats.get_day_pnl()
        if day_pnl <= -capital * config.DAILY_MAX_LOSS_PCT:
            return False, (
                f"DAILY LOSS LIMIT: ${day_pnl:.2f} exceeds "
                f"-{capital * config.DAILY_MAX_LOSS_PCT:.2f}"
            )

        return True, "ok"

    def position_size_multiplier(self, recent_wins: int, recent_losses: int) -> float:
        """Dynamic sizing from Polymarket-bot: reduce on losses, increase on wins."""
        if recent_losses >= 3:
            return 0.5
        if recent_losses >= 2:
            return 0.75
        if recent_wins >= 3:
            return 1.25
        return 1.0
