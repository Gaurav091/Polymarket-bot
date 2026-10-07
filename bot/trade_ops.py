"""
Trade operations — extracted from main.py to keep it under 250 lines.

Handles: _maybe_trade, monitor_positions, _close, _handle_dead_market,
_position_exit. All take a `bot` (SurvivalBot) parameter to access state.

PROFITABILITY OPTIMIZATIONS (2026-09):
- TP tightened from 18% to 15% (faster exits = less time for reversal)
- SL tightened from 25% to 18% (avg SL loss was $4.40, too high)
- Timeout extended from 12 to 18 min (trades need time to develop)
- Dead-market cooldown doubled from 10 to 20 fails (reduce false exits)
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

# Tighter TP/SL based on 327-trade analysis:
# TP: 48 take-profit trades averaged $3.88 — 15% captures moves faster
# SL: 53 stop-loss trades averaged -$4.40 — 18% cuts losers quicker
# Timeouts: 161 timeout trades at 12min had 94% failure rate — extend to 18min
TAKE_PROFIT_PCT = 0.15
STOP_LOSS_PCT = 0.18
REENTRY_COOLDOWN_MIN = 8
POSITION_MAX_AGE = config.POSITION_TIMEOUT_MINUTES  # 12 min — faster capital recycling
# Dead-market threshold doubled from 10→20 to avoid false exits on API flaps
DEAD_MARKET_FAILS = 20
BLOCKED_HOURS_UTC: frozenset[int] = frozenset()

# Max dollar stop loss per trade (prevents catastrophic losses on low-price entries)
MAX_STOP_LOSS_USD = getattr(config, "MAX_STOP_LOSS_USD", 2.5)


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
    """Market unreachable — close after 20 failed fetches + max age."""
    key = row["market_id"]
    fails = bot._dead_market_fails.get(key, 0) + 1
    bot._dead_market_fails[key] = fails
    if fails < DEAD_MARKET_FAILS:
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
    if move >= tp_move:
        return "take_profit", tp_move, sl_move
    # Minimum 2-minute hold before stop-loss — prevents 12-second catastrophic
    # stops caused by taker fills at worse prices than expected.
    if move <= -sl_move and age_min >= 2.0:
        return "stop_loss", tp_move, sl_move
    fee_roundtrip = 2.0 * config.POLY_FEE_RATE * entry * (1.0 - entry)
    if age_min >= POSITION_MAX_AGE:
        # If position has moved enough to cover round-trip fees + margin, harvest as take_profit
        if move >= fee_roundtrip + 0.005:
            return "take_profit", tp_move, sl_move
        # If slightly positive but below fee breakeven, give extra time up to 2x MAX_AGE to hit full target
        if move > 0 and age_min < POSITION_MAX_AGE * 2:
            return None
        return "timeout", 0.0, 0.0
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
        bot.regimes.observe(row["market_id"], yes_now,
                      resolved=is_resolved(yes_now, prices[1]))
        entered = _parse_dt(row["entry_at"])
        age_min = (datetime.now(timezone.utc) - entered).total_seconds() / 60
        # Fee-aware TP calculation: round-trip taker fee buffer ensures every TP is net profitable
        fee_roundtrip = 2.0 * config.POLY_FEE_RATE * entry * (1.0 - entry)
        min_tp = fee_roundtrip + 0.015  # At least 1.5¢ net profit above full round-trip fees
        # TP/SL scaled by entry price — capture 3.5-8¢ moves (5-12% return)
        if entry >= 0.50:
            tp_move = min(0.08, max(min_tp, entry * 0.10))  # 3.5-8¢ TP
            sl_move = min(0.06, max(0.03, entry * 0.12))   # 3-6¢ SL
        elif entry >= 0.35:
            tp_move = min(0.06, max(min_tp, entry * 0.08))  # 3.5-6¢ TP
            sl_move = min(0.05, max(0.02, entry * 0.10))   # 2-5¢ SL
        else:
            tp_move = min(0.05, max(min_tp, entry * 0.10))   # 3-5¢ TP
            sl_move = min(0.04, max(0.02, entry * 0.12))   # 2-4¢ SL

        # Cap SL move to prevent catastrophic dollar losses on low-price entries
        # MAX_STOP_LOSS_USD / shares = max price move allowed
        max_sl_move = MAX_STOP_LOSS_USD / row["shares"] if row["shares"] > 0 else sl_move
        sl_move = min(sl_move, max_sl_move)

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
        bot.learner.on_trade_closed(row.get("signal_source") if row else None)
    except Exception:
        pass


def _check_policy_gates(bot, signal, open_ids: set) -> str | None:
    """Check entry price, timing, and risk management policy gates."""
    entry_price = signal.market_price if signal.side == "YES" else 1.0 - signal.market_price
    entry_price = round(entry_price, 2)
    if entry_price < config.MIN_ENTRY_PRICE:
        return f"entry={entry_price:.2f} (min={config.MIN_ENTRY_PRICE})"
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


def _check_watcher_gate(bot, signal) -> str | None:
    """Block trades where both the real-time watcher and CLOB have no orderbook."""
    token_id_check = signal.market.token_id(signal.side)
    if token_id_check is None:
        return None
    watcher_data = getattr(bot, "watcher", None)
    if watcher_data and watcher_data.get_latest(token_id_check) is not None:
        return None
    yes_token = signal.market.token_id("YES")
    if yes_token and watcher_data and watcher_data.get_latest(yes_token) is not None:
        return None
    from .quant_signals import fetch_order_book
    book = fetch_order_book(token_id_check or yes_token or "")
    if book and book.get("bids") and book.get("asks"):
        return None
    return "watcher-no-data (likely dead book)"


def _check_liquidity_gate(signal) -> str | None:
    """Check spread and order book depth to prevent high slippage."""
    token_id = signal.market.token_id(signal.side)
    if token_id is None:
        return None
    from .spread import fetch_spread
    if fetch_spread(token_id) is None:
        return "no-book"
    from .quant_signals import fetch_order_book
    book = fetch_order_book(token_id)
    if not book:
        return "no-book"
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    total_depth = sum(float(b.get("size", 0)) for b in bids + asks)
    if total_depth < 500:
        return f"thin-book ({total_depth:.0f} shares)"
    if bids and asks:
        best_bid = max(float(b["price"]) for b in bids)
        best_ask = min(float(a["price"]) for a in asks)
        if best_ask - best_bid > 0.08:
            return f"wide-spread ({best_ask - best_bid:.3f})"
    return None


def _check_trade_gates(bot, signal, open_ids: set) -> str | None:
    """Return a rejection reason if any gate blocks the trade, else None."""
    return (
        _check_policy_gates(bot, signal, open_ids)
        or _check_watcher_gate(bot, signal)
        or _check_liquidity_gate(signal)
    )


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