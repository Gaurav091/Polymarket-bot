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
# Polymarket trades 24/7 — no blocked hours (was range(1,7) for US markets)
BLOCKED_HOURS_UTC: frozenset[int] = frozenset()


def _parse_dt(val) -> datetime:
    """Parse a datetime from SQLite (string or datetime object)."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return datetime.now(timezone.utc)


def _handle_dead_market(bot, row):
    """Market unreachable — close after 10 failed fetches + max age."""
    key = row["market_id"]
    fails = bot._dead_market_fails.get(key, 0) + 1
    bot._dead_market_fails[key] = fails
    if fails < 10:
        return
    entered = _parse_dt(row["entry_at"])
    age_min = (datetime.now(timezone.utc) - entered).total_seconds() / 60
    if age_min < POSITION_MAX_AGE:
        return
    log.warning(
        f"[monitor] market {key[:10]} unreachable {fails}x "
        f"and age {age_min:.0f}m ≥ {POSITION_MAX_AGE}m — closing at entry"
    )
    # entry_price is held-side price; close_position expects YES-side price
    exit_yes = row["entry_price"] if row["side"] == "YES" else 1.0 - row["entry_price"]
    close_position(row["id"], exit_yes, "dead_market",
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


def _watcher_prices(bot, market_id: str):
    """Look up real-time prices for a market via the watcher.
    Returns (yes_price, no_price) or None if unavailable."""
    if not bot.watcher:
        return None
    for m in bot.markets:
        if m.condition_id == market_id:
            tid = m.token_id("YES")
            if tid:
                update = bot.watcher.get_latest(tid)
                if update is not None:
                    return (update.yes_price, update.no_price)
            break
    return None


def monitor_positions(bot):
    """Check all open positions for TP/SL/timeout/exit conditions."""
    for row in journal.get_open_trades():
        entry = row["entry_price"]
        side = row["side"]
        prices = _watcher_prices(bot, row["market_id"])
        if prices is None:
            _handle_dead_market(bot, row)
            continue
        yes_now = prices[0]
        bot.regimes.update_market(row["market_id"], yes_now,
                                  resolved=is_resolved(yes_now, prices[1]))
        entered = _parse_dt(row["entry_at"])
        age_min = (datetime.now(timezone.utc) - entered).total_seconds() / 60
        tp_move = min(0.08, max(0.03, entry * TAKE_PROFIT_PCT))
        sl_floor = max(0.02, entry * 0.10)
        sl_move = min(0.06, max(sl_floor, entry * STOP_LOSS_PCT))
        exit_ = _position_exit(bot, row, prices, entry, side, age_min, tp_move, sl_move)
        if exit_:
            reason, tp_rec, sl_rec = exit_
            _close(bot, row["id"], yes_now, reason, row, tp_move=tp_rec, sl_move=sl_rec)


def _find_token_id(bot, row) -> str | None:
    """Find the token ID for a market position."""
    if row is None:
        return None
    for m in bot.markets:
        if m.condition_id == row["market_id"]:
            return m.token_id(row["side"])
    return None


def _track_loss(bot, row):
    """Increment per-market loss counter; log if circuit breaker trips."""
    if row is None:
        return
    mid = row["market_id"]
    losses = bot._market_losses.get(mid, 0) + 1
    bot._market_losses[mid] = losses
    if losses >= config.MARKET_LOSS_LIMIT:
        log.warning(f"[breaker] {mid[:8]} hit {losses} losses — blocked until question changes")


def _close(bot, trade_id: int, exit_yes_price: float, reason: str, row=None,
           tp_move: float = 0.0, sl_move: float = 0.0):
    """Close a position and update survival/learner state."""
    shares = row["shares"] if row else None
    token_id = _find_token_id(bot, row)
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
        _track_loss(bot, row)
    try:
        bot.learner.update_on_close(pnl, reason)
    except Exception:
        pass


def _check_trade_gates(bot, signal, open_ids: set) -> str | None:
    """Return a rejection reason if any gate blocks the trade, else None."""
    if signal.market_price < config.MIN_ENTRY_PRICE:
        entry = (signal.market_price if signal.side == "YES"
                 else 1.0 - signal.market_price)
        if entry < config.MIN_ENTRY_PRICE:
            return f"entry={entry:.2f} (min={config.MIN_ENTRY_PRICE})"
    utc_hour = datetime.now(timezone.utc).hour
    if utc_hour in BLOCKED_HOURS_UTC:
        return f"blocked hour {utc_hour}"
    if not bot.regimes.can_trade(signal.market.condition_id):
        return "regime-cooloff"
    if signal.market.condition_id in open_ids:
        return "already open"
    cooldown = getattr(bot.learner, "_reentry_cooldown", {})
    if signal.market.condition_id in cooldown:
        return "cooldown"
    blocked = bot._market_losses
    if signal.market.condition_id in blocked:
        return f"loss-blocked ({blocked[signal.market.condition_id]} losses)"
    if len(open_ids) >= config.MAX_OPEN_POSITIONS:
        return f"{len(open_ids)} open >= max {config.MAX_OPEN_POSITIONS}"
    if bot.risk.state.halted:
        return f"risk-halted: {bot.risk.state.halt_reason}"
    return None


def _maybe_trade(bot, signal):
    """Evaluate and execute a trade signal if all gates pass."""
    log = __import__("logging").getLogger(__name__)
    open_ids = {r["market_id"] for r in journal.get_open_trades()}
    reject = _check_trade_gates(bot, signal, open_ids)
    if reject:
        log.info(f"[trade] skip {signal.market.question[:40]} — {reject}")
        return
    recent = get_recent_results(5)
    risk_mult = bot.risk.position_size_multiplier(
        recent.count("win"), recent.count("loss"),
    )
    learner_mult = bot.learner.get_position_size_adjustment()
    signal.bet_amount = round(
        max(config.MIN_BET_USD, signal.bet_amount) * risk_mult * learner_mult, 2
    )
    if signal.bet_amount < config.MIN_BET_USD:
        log.info(f"[trade] SKIP bet ${signal.bet_amount:.2f} < MIN ${config.MIN_BET_USD}")
        return
    _execute_and_log(bot, signal)


def _execute_and_log(bot, signal):
    """Execute trade and log result."""
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
        log.info(f"[trade] REJECTED {signal.side} {signal.market.question[:40]} — {result}")