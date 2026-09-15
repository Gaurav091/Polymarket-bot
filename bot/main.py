"""Survival Bot — main loop. Earn within window or die."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from . import config
from . import journal
from .journal_stats import get_stats, get_day_pnl
from .calibration import is_resolved
from .markets import fetch_active_markets, filter_niche
from .spread import filter_by_spread
from .news import NewsPoller
from .regime import RegimeTracker
from .risk import RiskManager
from .learner import Learner
from .survival import SurvivalMonitor, VitalState
from .watcher import MarketPriceWatcher
from . import scanners
from . import trade_ops

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
log = logging.getLogger("survival-bot")

TAKE_PROFIT_PCT = 0.18
STOP_LOSS_PCT = 0.25
REENTRY_COOLDOWN_MIN = 8
POSITION_MAX_AGE = config.POSITION_TIMEOUT_MINUTES or 99999
BLOCKED_HOURS_UTC = frozenset(range(1, 7))


def on_death(status):
    """Death callback — log the obituary."""
    journal.log_survival_event(
        "death",
        f"survived {status.time_since_profit/60:.1f}m without profit; "
        f"earned=${status.total_realized_profit:.2f} "
        f"lost=${status.total_realized_loss:.2f}",
    )
    log.error("=" * 60)
    log.error("BOT DIED — no profit earned within the survival window")
    log.error(f"  Time since last profit: {status.time_since_profit/60:.1f} minutes")
    log.error(f"  Total earned: ${status.total_realized_profit:.2f}")
    log.error(f"  Total lost:   ${status.total_realized_loss:.2f}")
    log.error("=" * 60)


class SurvivalBot:
    def __init__(self):
        self.survival = SurvivalMonitor(on_death=on_death)
        self.risk = RiskManager()
        self.learner = Learner()
        self.news = NewsPoller()
        self.regimes = RegimeTracker()
        self.watcher = MarketPriceWatcher()
        self.markets: list = []
        self.last_market_refresh = 0.0
        self._api_attempts = 0
        self._api_errors = 0
        self._dead_market_fails: dict[str, int] = {}
        self._last_cal_check = 0.0
        self.stats = {"news": 0, "matched": 0, "signals": 0, "trades": 0, "closes": 0}
        self.current_state = VitalState.BOOT

    # ------------------------------------------------------------
    # Circuit breaker (poly-maker pattern)
    # ------------------------------------------------------------
    def _note_api_result(self, ok: bool):
        self._api_attempts += 1
        if not ok:
            self._api_errors += 1

    @property
    def api_error_rate(self) -> float:
        if self._api_attempts < 10:
            return 0.0
        return self._api_errors / self._api_attempts

    # ------------------------------------------------------------
    # Market cache
    # ------------------------------------------------------------
    def refresh_markets(self):
        if time.time() - self.last_market_refresh < 300:  # 5 min cache
            return
        all_markets = fetch_active_markets(limit=500)
        self._note_api_result(bool(all_markets))
        # Feed price observations into the regime machine (event detection)
        for m in all_markets:
            self.regimes.observe(m.condition_id, m.yes_price, resolved=is_resolved(m.yes_price, m.no_price))
        self.markets = filter_niche(all_markets)
        # Phase 2: spread filter — reject wide-spread markets
        before_count = len(self.markets)
        self.markets = filter_by_spread(self.markets, max_spread=config.MAX_SPREAD_USD)
        spread_rejected = before_count - len(self.markets)
        self.last_market_refresh = time.time()
        log.info(
            f"[markets] {len(self.markets)} niche markets tracked "
            f"(of {len(all_markets)} fetched, {spread_rejected} wide-spread rejected)"
        )
        # Update watcher tokens
        token_ids = []
        for m in self.markets:
            tid = m.token_id("YES")
            if tid:
                token_ids.append(tid)
        self.watcher.watch_tokens(token_ids)

    # ------------------------------------------------------------
    # Quant scan — Python-native signals, no LLM, no news needed
    # ------------------------------------------------------------
    def _timesfm_scores(self, scan_markets: list) -> dict:
        """Batched TimesFM forecast (delegated to scanners.py)."""
        return scanners.timesfm_scores(scan_markets)

    def _quant_signal_for(self, market, tfm_scores: dict, emergency: bool):
        """Score one market with the ensemble (delegated to scanners.py)."""
        return scanners.quant_signal_for(
            market, tfm_scores, emergency, self.learner,
        )

    def quant_scan(self):
        """Score tracked markets (delegated to scanners.py)."""
        scanners.run_quant_scan(self)

    # ------------------------------------------------------------
    # Kalshi cross-platform arbitrage scan
    # ------------------------------------------------------------
    def arb_scan(self):
        """Check for guaranteed arbitrage (delegated to scanners.py)."""
        scanners.run_arb_scan(self)

    # ------------------------------------------------------------
    # News → signal → trade
    # ------------------------------------------------------------
    def process_news(self):
        """Poll news and fire trades (delegated to scanners.py)."""
        scanners.run_news_scan(self)

    def _maybe_trade(self, signal):
        return trade_ops._maybe_trade(self, signal)

    # ------------------------------------------------------------
    # Position monitoring — this is where profit is realized
    # ------------------------------------------------------------
    def _handle_dead_market(self, row):
        return trade_ops._handle_dead_market(self, row)

    def _position_exit(self, row, prices, entry, side, age_min, tp_move, sl_move):
        return trade_ops._position_exit(self, row, prices, entry, side, age_min, tp_move, sl_move)

    def monitor_positions(self):
        return trade_ops.monitor_positions(self)

    def _close(self, trade_id: int, exit_yes_price: float, reason: str, row=None,
               tp_move: float = 0.0, sl_move: float = 0.0):
        return trade_ops._close(self, trade_id, exit_yes_price, reason, row, tp_move, sl_move)

    # ------------------------------------------------------------
    # Main loop — extracted helpers to keep run() under complexity limit
    # ------------------------------------------------------------
    def _run_heartbeat(self) -> VitalState:
        state = self.survival.check()
        self.current_state = state
        print(self.survival.summary())
        return state

    def _run_risk_check(self) -> bool:
        day_pnl = get_day_pnl()
        equity = config.CAPITAL_USD + day_pnl
        allowed, reason = self.risk.check(equity)
        if not allowed and not self.risk.state.halted:
            log.warning(f"[risk] trading paused: {reason}")
        if self.api_error_rate >= 0.5:
            log.error("[breaker] API error rate ≥ 50% — halting entries (stale data risk)")
            allowed = False
        return allowed

    def _run_calibration_check(self):
        if time.time() - self._last_cal_check <= 300:
            return
        try:
            from .journal import check_resolved_markets
            resolved = check_resolved_markets()
            if resolved:
                log.info(f"[calibration] {resolved} markets resolved, accuracy updated")
        except Exception as e:
            log.debug(f"[calibration] check error: {e}")
        self._last_cal_check = time.time()

    def _run_trading_cycle(self):
        allowed = self._run_risk_check()
        self.monitor_positions()  # TP/SL must never be delayed by slow scans
        self._run_calibration_check()
        if allowed:
            self.refresh_markets()
            self.process_news()
            self.quant_scan()
            self.arb_scan()

    def _death_report(self):
        stats = get_stats()
        log.info(f"[final] trades closed: {stats['closed_trades']} | "
                 f"win rate: {stats['win_rate']:.0f}% | "
                 f"total PnL: ${stats['total_pnl']:.2f}")
        log.info("[final] BOT TERMINATED — survival condition failed")

    def run(self):
        journal.init_db()
        mode = "PAPER" if config.DRY_RUN else "LIVE"
        log.info("=" * 60)
        log.info("SURVIVAL BOT — earn within the window or die")
        log.info(f"  Mode: {mode} | Capital: ${config.CAPITAL_USD}")
        log.info(f"  Survival window: {config.SURVIVAL_WINDOW_MINUTES}m "
                 f"(grace: {config.SURVIVAL_GRACE_MINUTES}m)")
        log.info(f"  Survival mode: {'ON' if config.SURVIVAL_ENABLED else 'OFF'}")
        log.info("=" * 60)
        journal.log_survival_event("boot", f"mode={mode}")

        try:
            self.watcher.start()
        except Exception as e:
            log.debug(f"[watcher] failed to start: {e}")

        while True:
            loop_start = time.time()
            if self._run_heartbeat() == VitalState.DEAD:
                break
            self._run_trading_cycle()
            time.sleep(max(1.0, config.SCAN_INTERVAL_SECONDS - (time.time() - loop_start)))

        self._death_report()
        self.watcher.stop()


def main():
    bot = SurvivalBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        log.info("Interrupted by user — shutting down.")


if __name__ == "__main__":
    main()
