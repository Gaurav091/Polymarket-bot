"""
WebSocket price streaming — extracted from watcher.py.

Handles WS connection, reconnection, message parsing, and fallback polling.
The MarketPriceWatcher class in watcher.py delegates to these functions.
"""
from __future__ import annotations

import json
import logging
import time

log = logging.getLogger(__name__)

MARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
RECONNECT_DELAY = 5.0
MAX_RECONNECT_DELAY = 60.0
HEARTBEAT_INTERVAL = 30.0


def _ws_connect_and_subscribe(w):
    """Establish WS connection and subscribe to watched tokens."""
    import websocket
    w._ws = websocket.create_connection(MARKET_WS_URL, timeout=10)
    w._reconnect_delay = RECONNECT_DELAY
    log.info("[watcher] WS connected")
    if w._watching:
        sub_msg = json.dumps({
            "type": "subscribe",
            "channel": "market",
            "assets_ids": list(w._watching),
        })
        w._ws.send(sub_msg)
    w._ws.settimeout(HEARTBEAT_INTERVAL)
    w._last_heartbeat = time.time()


def _ws_recv_loop(w):
    """Process incoming WS messages until error or timeout."""
    import websocket
    while w._running and w._use_ws:
        try:
            msg = w._ws.recv()
            _handle_ws_message(w, msg)
            w._last_heartbeat = time.time()
        except websocket.WebSocketTimeoutException:
            if time.time() - w._last_heartbeat > HEARTBEAT_INTERVAL * 2:
                log.debug("[watcher] WS heartbeat timeout, reconnecting")
                break
        except Exception as e:
            log.debug("[watcher] WS recv error: %s", e)
            break


def _run_ws(w):
    """WebSocket price streaming. `w` is the MarketPriceWatcher instance."""
    try:
        import websocket  # noqa: F401
    except ImportError:
        log.debug("[watcher] websocket-client not installed, using polling")
        w._use_ws = False
        return

    while w._running and w._use_ws:
        try:
            _ws_connect_and_subscribe(w)
            _ws_recv_loop(w)
        except Exception as e:
            log.debug("[watcher] WS connection error: %s", e)
        if w._running and w._use_ws:
            time.sleep(w._reconnect_delay)
            w._reconnect_delay = min(w._reconnect_delay * 2, MAX_RECONNECT_DELAY)


def _handle_ws_message(w, msg: str):
    """Process a WebSocket message."""
    try:
        data = json.loads(msg)
    except json.JSONDecodeError:
        return
    msg_type = data.get("type", "")
    if msg_type == "price_change":
        token_id = data.get("asset_id", "")
        if token_id and token_id in w._watching:
            price = float(data.get("price", 0))
            _update_price(w, token_id, price)
    elif msg_type == "book":
        token_id = data.get("asset_id", "")
        if token_id and token_id in w._watching:
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            if bids and asks:
                best_bid = max(float(b["price"]) for b in bids)
                best_ask = min(float(a["price"]) for a in asks)
                mid = (best_bid + best_ask) / 2
                _update_price(w, token_id, mid)


def _update_price(w, token_id: str, price: float):
    """Update price and calculate momentum."""
    from .watcher import _PriceTracker, PriceUpdate

    now = time.time()
    tracker = w._trackers.get(token_id)
    if tracker is None:
        tracker = _PriceTracker()
        w._trackers[token_id] = tracker
    if tracker.last_time > 0 and tracker.last_price > 0:
        dt = now - tracker.last_time
        if dt > 0:
            dp = price - tracker.last_price
            alpha = 0.3
            tracker.momentum = alpha * (dp / dt) + (1 - alpha) * tracker.momentum
    tracker.last_price = price
    tracker.last_time = now
    update = PriceUpdate(
        token_id=token_id,
        yes_price=price,
        no_price=1.0 - price,
        timestamp=now,
        momentum=tracker.momentum,
    )
    w._latest[token_id] = update
    for cb in w._callbacks:
        try:
            cb(update)
        except Exception as e:
            log.debug("[watcher] callback error: %s", e)


def _run_polling(w):
    """Fallback polling mode (uses existing CLOB API)."""
    while w._running and not w._use_ws:
        if not w._watching:
            time.sleep(5)
            continue
        try:
            from .markets import fetch_batch_prices
            prices = fetch_batch_prices(list(w._watching))
            for tid, (yes_p, _no_p) in prices.items():
                _update_price(w, tid, yes_p)
        except Exception as e:
            log.debug("[watcher] polling error: %s", e)
        time.sleep(2)

