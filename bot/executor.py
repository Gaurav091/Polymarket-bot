"""
Executor — paper trading by default, live via py-clob-client when DRY_RUN=false.

Enforces Polymarket CLOB minimums (from Polymarket-bot):
- price * size >= $1
- size >= 5 shares

Live path (verified against installed py-clob-client API surface):
- Entries: market BUY (FAK) — we want fills, not resting quotes
- Exits: market SELL (FAK) of held shares
- Prices rounded to the market's tick size (0.1/0.01/0.001/0.0001)
"""
from __future__ import annotations

import logging

from . import config
from . import journal
from .edge import Signal
from .markets import MIN_ORDER_SIZE_SHARES, MIN_ORDER_VALUE_USDC

log = logging.getLogger(__name__)


def _shares_for(bet_amount: float, price: float) -> float:
    return round(bet_amount / price, 2)


def _meets_minimums(shares: float, price: float) -> bool:
    return shares * price >= MIN_ORDER_VALUE_USDC and shares >= MIN_ORDER_SIZE_SHARES


def _round_to_tick(price: float, tick: float) -> float:
    """Round a price to a valid tick increment (e.g. tick=0.01 → 2 decimals)."""
    decimals = len(str(tick).split(".")[1]) if "." in str(tick) else 0
    return round(round(price / tick) * tick, decimals)


def _make_client():
    """Build an authenticated ClobClient. Returns None if not configured."""
    from py_clob_client.client import ClobClient

    if not config.POLYMARKET_PRIVATE_KEY:
        log.error("[executor] POLYMARKET_PRIVATE_KEY not set — cannot trade live")
        return None
    client = ClobClient(
        host=config.CLOB_HOST,
        key=config.POLYMARKET_PRIVATE_KEY,
        chain_id=137,
    )
    client.set_api_creds(client.create_or_derive_api_creds())
    return client


def execute_trade(signal: Signal) -> dict:
    """Open a position. Paper mode logs to journal; live mode posts to CLOB."""
    price = signal.market_price if signal.side == "YES" else 1 - signal.market_price
    shares = _shares_for(signal.bet_amount, price)

    if not _meets_minimums(shares, price):
        return {
            "status": "rejected_minimums",
            "reason": f"shares={shares} price={price:.3f} below CLOB minimums",
        }

    order_id = None
    if not config.DRY_RUN:
        result = _execute_live(signal, price, shares)
        if result["status"] != "executed":
            return result
        order_id = result["order_id"]

    trade_id = journal.log_trade_open(
        market_id=signal.market.condition_id,
        question=signal.market.question,
        side=signal.side,
        entry_price=price,
        amount_usd=signal.bet_amount,
        shares=shares,
        edge=signal.edge,
        reasoning=signal.reasoning,
        headline=signal.headline,
        news_source=signal.news_source,
        classification=signal.classification,
        materiality=signal.materiality,
        signal_source=signal.signal_source,
    )
    return {"status": "executed", "trade_id": trade_id, "order_id": order_id, "shares": shares}


def _execute_live(signal: Signal, price: float, shares: float) -> dict:
    """Place a real market BUY via Polymarket CLOB (FAK — fill or kill)."""
    try:
        from py_clob_client.clob_types import MarketOrderArgs, OrderType

        client = _make_client()
        if client is None:
            return {"status": "error_not_configured"}

        token_id = signal.market.token_id(signal.side)
        if not token_id:
            return {"status": "error_no_token"}

        # Round to the market's tick size to avoid order rejection
        tick = float(client.get_tick_size(token_id))
        limit_price = _round_to_tick(min(price + 0.02, 0.99), tick)  # slippage buffer

        order_args = MarketOrderArgs(
            token_id=token_id,
            amount=round(shares * limit_price, 2),  # USD notional for market BUY
            price=limit_price,
            side="BUY",
        )
        signed = client.create_market_order(order_args)
        resp = client.post_order(signed, OrderType.FAK)  # type: ignore[arg-type] — py-clob-client enum typing quirk
        order_id = resp.get("orderID", resp.get("id", "unknown")) if isinstance(resp, dict) else str(resp)
        return {"status": "executed", "order_id": order_id}

    except ImportError:
        return {"status": "error_no_clob_client"}
    except Exception as e:
        log.warning(f"[executor] live order failed: {type(e).__name__}: {e}")
        return {"status": f"error_{type(e).__name__}"}


def _close_live(token_id: str, shares: float, ref_price: float) -> dict:
    """Sell held shares at market (FAK). ref_price = current price of the held token."""
    try:
        from py_clob_client.clob_types import MarketOrderArgs, OrderType

        client = _make_client()
        if client is None:
            return {"status": "error_not_configured"}

        tick = float(client.get_tick_size(token_id))
        # SELL buffer: accept slightly below current price to ensure fill
        limit_price = _round_to_tick(max(ref_price - 0.02, 0.01), tick)

        order_args = MarketOrderArgs(
            token_id=token_id,
            amount=shares,  # share count for market SELL
            price=limit_price,
            side="SELL",
        )
        signed = client.create_market_order(order_args)
        resp = client.post_order(signed, OrderType.FAK)  # type: ignore[arg-type] — py-clob-client enum typing quirk
        order_id = resp.get("orderID", resp.get("id", "unknown")) if isinstance(resp, dict) else str(resp)
        return {"status": "executed", "order_id": order_id}

    except ImportError:
        return {"status": "error_no_clob_client"}
    except Exception as e:
        log.warning(f"[executor] live close failed: {type(e).__name__}: {e}")
        return {"status": f"error_{type(e).__name__}"}


def close_position(trade_id: int, exit_yes_price: float, status: str = "closed",
                   token_id: str | None = None, shares: float | None = None,
                   entry_row=None, tp_move: float = 0.0, sl_move: float = 0.0) -> float:
    """Close a position at the given YES price. Returns realized PnL.

    In live mode, first sells the real shares on CLOB (paper mode skips this).
    entry_row, tp_move, sl_move are forwarded to journal.log_trade_close
    for tp_hit/sl_hit tracking.
    """
    if not config.DRY_RUN and token_id and shares:
        # Price of the token we hold: YES token exits at exit_yes_price,
        # NO token exits at 1 - exit_yes_price (caller passes YES price)
        result = _close_live(token_id, shares, exit_yes_price)
        if result["status"] != "executed":
            log.warning(f"[executor] live close failed ({result['status']}) — journaling anyway")

    pnl = journal.log_trade_close(trade_id, exit_yes_price, status,
                                 entry_row=entry_row, tp_move=tp_move, sl_move=sl_move)
    return pnl
