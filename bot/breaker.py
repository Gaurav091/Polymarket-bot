"""
Per-market loss circuit breaker.

After N losses on one market, block it until the question text changes.
"""
from __future__ import annotations

import logging

from . import config, journal

log = logging.getLogger(__name__)


def load_market_losses(bot) -> None:
    """Load historical loss counts from DB on startup."""
    try:
        conn = journal._conn()
        rows = conn.execute(
            """SELECT market_id, COUNT(*) as losses
               FROM trades WHERE pnl_usd < 0 AND status = 'closed'
               GROUP BY market_id"""
        ).fetchall()
        conn.close()
        for r in rows:
            if r["losses"] >= config.MARKET_LOSS_LIMIT:
                bot._market_losses[r["market_id"]] = r["losses"]
        if bot._market_losses:
            log.info(f"[breaker] loaded {len(bot._market_losses)} loss-blocked markets from DB")
    except Exception as e:
        log.debug(f"[breaker] load error: {e}")


def check_question_changes(bot, all_markets) -> None:
    """Reset circuit breaker for markets whose question text has changed."""
    for m in all_markets:
        prev = bot._market_questions.get(m.condition_id)
        if prev is not None and prev != m.question and m.condition_id in bot._market_losses:
            del bot._market_losses[m.condition_id]
            log.info(f"[breaker] question changed for {m.condition_id[:8]} — block reset")
        bot._market_questions[m.condition_id] = m.question
