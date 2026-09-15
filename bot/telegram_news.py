"""
Telegram news stream — real-time news via Telegram Bot API long polling.

Faster than RSS (seconds vs minutes), no Twitter API OAuth overhead.
Requires: TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_IDS in .env.

Uses `requests` (never httpx/aiohttp — both hang on this machine).
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Thread
from typing import Callable

import requests

from . import config
from .news import NewsEvent

log = logging.getLogger(__name__)

TG_API = "https://api.telegram.org"


@dataclass
class TelegramNewsStream:
    """Long-poll Telegram for new channel messages and emit them as NewsEvents."""
    bot_token: str
    channel_ids: list[str]
    callback: Callable[[NewsEvent], None]
    poll_interval: float = 5.0

    def start(self):
        self._thread = Thread(target=self._run, daemon=True, name="telegram-news")
        self._running = True
        self._thread.start()
        log.info(f"[telegram] Stream started — monitoring {len(self.channel_ids)} channel(s)")

    def stop(self):
        self._running = False

    def _run(self):
        offset = 0
        while self._running:
            updates = self._fetch_updates(offset)
            for update in updates:
                offset = update["update_id"]
                self._dispatch(update)
            if not updates:
                time.sleep(self.poll_interval)

    def _fetch_updates(self, offset: int) -> list:
        try:
            resp = requests.get(
                f"{TG_API}/bot{self.bot_token}/getUpdates",
                params={"offset": offset + 1, "timeout": 30},
                timeout=35,
                verify=False,
            )
            return resp.json().get("result", [])
        except Exception as e:
            log.debug(f"[telegram] poll error: {e}")
            return []

    def _dispatch(self, update: dict):
        msg = update.get("channel_post") or update.get("message", {})
        text = msg.get("text", "")
        if not text:
            return
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if self.channel_ids and chat_id not in self.channel_ids:
            return
        event = NewsEvent(
            headline=text[:500],
            source="telegram",
            url=f"https://t.me/{chat_id}/{msg.get('message_id', '')}",
            received_at=datetime.now(timezone.utc),
        )
        try:
            self.callback(event)
        except Exception as e:
            log.debug(f"[telegram] callback error: {e}")


def start_telegram_if_configured(callback: Callable[[NewsEvent], None]) -> TelegramNewsStream | None:
    """Kick off the Telegram stream if credentials are present in .env."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    raw_channels = os.getenv("TELEGRAM_CHANNEL_IDS", "").strip()
    if not token or not raw_channels:
        log.debug("[telegram] TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_IDS not set — skipping")
        return None

    channel_ids = [c.strip() for c in raw_channels.split(",") if c.strip()]
    stream = TelegramNewsStream(
        bot_token=token,
        channel_ids=channel_ids,
        callback=callback,
    )
    stream.start()
    return stream
