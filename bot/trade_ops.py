"""
Trade operations — extracted from main.py to keep it under 250 lines.

Handles: _maybe_trade, monitor_positions, _close, _handle_dead_market,
_position_exit. All take a `bot` (SurvivalBot) parameter to access state.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import config
from . import journal
from .calibration import is_resolved
from .executor import close_position, execute_trade
from .journal_stats import get_recent_results
from .risk import RiskManager
from .survival import VitalState
import logging

log = logging.getLogger(__name__)

TAKE_PROFIT_PCT = 0.18
STOP_LOSS_PCT = 0.25
REENTRY_COOLDOWN_MIN = 8
POSITION_MAX_AGE = config.POSITION_TIMEOUT_MINUTES or 99999
BLOCKED_HOURS_UTC = frozenset(range(1, 7))


def _handle_dead_market(bot, row):
    """Market unreachable — close after 10 failed fetches + max age."""
    key = row["market_id"]
    fails = bot._dead_market_fails.get(key, 0) + 1
    bot._dead_market_fails[key] = fails
    if fails < 10:
        return
    entered = row["entry_at"]
    if entered.tzinfo is None:
        entered = entered.replace(tzinfo=timezone.utc)
    age_min = (datetime.now(timezone.utc) - entered).total_seconds() / 60
    if age_min < POSITION_MAX_AGE:
        return
    log.warning(
        f"[monitor] market {key[:10]} unreachable {fails}x "
        f"and age {age_min:.0f}m ≥ {POSITION_MAX_AGE}m — closing at entry"
    )
    close_position(row["id"], row["entry_price"], "dead_market",
                   token_id=None, shares=row["shares"],
                   entry_row=row, tp_move=0.0, sl_move=0.0)


def _position_exit(bot, row, prices, entry, side, age_min, tp_move, sl_move):
    """Decide whether a live position should close now."""
    yes_now, no_now = prices
    if is_resolved(yes_now, no_now):
        return "resolved", 0.0, 0.0
    now_price = yes_now if side == "YES" else 1 - yes_now
    move = now_price - entry
    if bot.current_state == VitalState.CRITICAL:
        unrealized = move * row["shares"]
        reason = "survival_take" if unrealized >= 0.02 else "survival_cut"
        return reason, tp_move, sl_move
    if age_min >= POSITION_MAX_AGE:
        return "timeout", 0.0, 0.0
    if move >= tp_move:
        return "take_profit", tp_move, sl_move
    if move <= -sl_move:
        return "stop_loss", tp_move, sl_move
    return None


def monitor_positions(bot):
    """Check all open positions for TP/SL/timeout/exit conditions."""
    for row in journal.get_open_trades():
        entry = row["entry_price"]
        side = row["side"]
        prices = bot.watcher.get_prices(row["market_id"]) if bot.watcher else None
        if prices is None:
            _handle_dead_market(bot, row)
            continue
        yes_now = prices[0]
        bot.regimes.update_market(row["market_id"], yes_now,
                                  resolved=is_resolved(yes_now, prices[1]))
        entered = row["entry_at"]
        if entered.tzinfo is None:
            entered = entered.replace(tzinfo=timezone.utc)
        age_min = (datetime.now(timezone.utc) - entered).total_seconds() / 60
        tp_move = min(0.08, max(0.03, entry * TAKE_PROFIT_PCT))
        sl_floor = max(0.02, entry * 0.10)
        sl_move = min(0.06, max(sl_floor, entry * STOP_LOSS_PCT))
        exit_ = _position_exit(bot, row, prices, entry, side, age_min, tp_move, sl_move)
        if exit_:
            reason, tp_rec, sl_rec = exit_
            _close(bot, row["id"], yes_now, reason, row, tp_move=tp_rec, sl_move=sl_rec)


def _close(bot, trade_id: int, exit_yes_price: float, reason: str, row=None,
           tp_move: float = 0.0, sl_move: float = 0.0):
    """Close a position and update survival/learner state."""
    token_id = None
    shares = None
    if row is not None:
        shares = row["shares"]
        for m in bot.markets:
            if m.condition_id == row["market_id"]:
                token_id = m.token_id(row["side"])
                break
    pnl = close_position(trade_id, exit_yes_price, reason,
                        token_id=token_id, shares=shares,
                        entry_row=row, tp_move=tp_move, sl_move=sl_move)
    bot.stats["closes"] += 1
    if pnl > 0:
        bot.survival.record_profit(pnl)
        log.info(f"[close] {reason} +${pnl:.2f} — survival clock reset")
    else:
        bot.survival.record_loss(pnl)
        log.info(f"[close] {reason} ${pnl:.2f}")
    try:
        bot.learner.update_on_close(pnl, reason)
    except Exception:
        pass


def _maybe_trade(bot, signal):
    """Evaluate and execute a trade signal if all gates pass."""
    log = __import__("logging").getLogger(__name__)
    if signal.market_price < config.MIN_ENTRY_PRICE:
        return
    utc_hour = datetime.now(timezone.utc).hour
    if utc_hour in BLOCKED_HOURS_UTC:
        return
    if not bot.regimes.can_trade(signal.market.condition_id):
        log.debug(f"[regime] skip {signal.market.condition_id[:10]} — EVENT cooloff")
        return
    open_ids = {r["market_id"] for r in journal.get_open_trades()}
    if signal.market.condition_id in open_ids:
        return
    on_cooldown = getattr(bot.learner, "_reentry_cooldown", {})
    if signal.market.condition_id in on_cooldown:
        return
    blocked = getattr(bot.learner, "_loss_blocked", {})
    if signal.market.condition_id in blocked:
        return
    open_count = len(open_ids)
    if open_count >= config.MAX_OPEN_POSITIONS:
        return
    if bot.risk.state.halted:
        return
    recent = get_recent_results(5)
    wins = recent.count("win")
    losses = recent.count("loss")
    risk_mult = bot.risk.position_size_multiplier(wins, losses)
    learner_mult = bot.learner.position_size_multiplier()
    signal.bet_amount = round(
        max(config.MIN_BET_USD, signal.bet_amount) * risk_mult * learner_mult, 2
    )
    if signal.bet_amount < config.MIN_BET_USD:
        return
    result = execute_trade(signal)
    if result["status"] == "executed":
        bot.stats["trades"] += 1
        log.info(
            f"[trade] OPEN {signal.side} {signal.market.condition_id[:8]} "
            f"@ {signal.market_price:.2f} edge={signal.edge:.2f} — "
            f"{signal.signal_source}"
        )
        try:
            from .journal import log_calibration_signal
            log_calibration_signal(
                signal.market.condition_id,
                signal.market.question,
                signal_source=signal.signal_source or "unknown",
                predicted_direction=signal.side,
                predicted_materiality=signal.materiality,
                market_price_at_signal=signal.market_price,
            )
        except Exception:
            pass
    else:
        log.debug(f"[trade] rejected: {result}")