"""
WebSocket price watcher — real-time price updates from Polymarket CLOB.
Falls back to polling if WebSocket is unavailable.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

MARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
RECONNECT_DELAY = 5.0
MAX_RECONNECT_DELAY = 60.0
HEARTBEAT_INTERVAL = 30.0


@dataclass
class PriceUpdate:
    """A real-time price update from WebSocket."""
    token_id: str
    yes_price: float
    no_price: float
    timestamp: float
    momentum: float = 0.0  # price change velocity (¢/sec)


@dataclass
class _PriceTracker:
    """Internal tracker for momentum calculation."""
    last_price: float = 0.0
    last_time: float = 0.0
    momentum: float = 0.0


class MarketPriceWatcher:
    """Watches Polymarket prices via WebSocket with fallback to polling.
    
    Usage:
        watcher = MarketPriceWatcher()
        watcher.on_price_update(my_callback)
        watcher.watch_tokens(["token_id_1", "token_id_2"])
        watcher.start()  # runs in background thread
        # ... later ...
        watcher.stop()
    """
    
    def __init__(self):
        self._trackers: dict[str, _PriceTracker] = {}
        self._latest: dict[str, PriceUpdate] = {}
        self._callbacks: list[Callable[[PriceUpdate], None]] = []
        self._watching: set[str] = set()
        self._running = False
        self._thread: threading.Thread | None = None
        self._use_ws = True  # try WS first, fall back to polling
        self._ws = None
        self._last_heartbeat = 0.0
        self._reconnect_delay = RECONNECT_DELAY
    
    def on_price_update(self, callback: Callable[[PriceUpdate], None]):
        """Register a callback for price updates."""
        self._callbacks.append(callback)
    
    def watch_tokens(self, token_ids: list[str]):
        """Add tokens to the watch list."""
        self._watching.update(token_ids)
        for tid in token_ids:
            if tid not in self._trackers:
                self._trackers[tid] = _PriceTracker()
    
    def unwatch_tokens(self, token_ids: list[str]):
        """Remove tokens from the watch list."""
        for tid in token_ids:
            self._watching.discard(tid)
            self._trackers.pop(tid, None)
            self._latest.pop(tid, None)
    
    def get_latest(self, token_id: str) -> PriceUpdate | None:
        """Get the most recent price update for a token."""
        return self._latest.get(token_id)
    
    def get_all_latest(self) -> dict[str, PriceUpdate]:
        """Get all latest price updates."""
        return dict(self._latest)
    
    def start(self):
        """Start the watcher in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="price-watcher")
        self._thread.start()
        log.info("[watcher] started")
    
    def stop(self):
        """Stop the watcher."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        log.info("[watcher] stopped")
    
    def _run(self):
        """Main watcher loop — tries WS, falls back to polling."""
        from .watcher_ws import _run_ws, _run_polling
        while self._running:
            if self._use_ws:
                try:
                    _run_ws(self)
                except Exception as e:
                    log.debug(f"[watcher] WS failed: {e}, falling back to polling")
                    self._use_ws = False
            else:
                _run_polling(self)
    
    def _run_ws(self):
        """WebSocket price streaming (delegated to watcher_ws)."""
        from .watcher_ws import _run_ws
        _run_ws(self)
    
    def _handle_ws_message(self, msg: str):
        """Process a WebSocket message (delegated to watcher_ws)."""
        from .watcher_ws import _handle_ws_message
        _handle_ws_message(self, msg)
    
    def _update_price(self, token_id: str, price: float):
        """Update price and calculate momentum (delegated to watcher_ws)."""
        from .watcher_ws import _update_price
        _update_price(self, token_id, price)
    
    def _run_polling(self):
        """Fallback polling mode (delegated to watcher_ws)."""
        from .watcher_ws import _run_polling
        _run_polling(self)
