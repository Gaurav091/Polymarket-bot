"""
HTTP watchdog — hard wall-clock cap on every outbound request.

requests' timeout only bounds the gap between bytes, not total duration.
A dribbling response can stall a request indefinitely (observed: a gamma
fetch hung the whole bot loop for 43 minutes — no survival checks, no
position timeouts, death 20 minutes late). This module runs every request
in a worker thread and abandons it if it exceeds the cap.

Also provides:
- Connection pooling via requests.Session (TCP reuse, fewer ConnectionResetError)
- Retry with exponential backoff on transient errors (ConnectionResetError, etc.)
- Circuit breaker: after 4 consecutive failures, fail-fast for 30s
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import requests

log = logging.getLogger(__name__)

_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="http")
_HARD_CAP = 30.0  # seconds, wall-clock, non-negotiable

# --- Transient errors that warrant retry -----------------------------------------
_TRANSIENT_ERRORS = (
    ConnectionResetError,
    ConnectionAbortedError,
    ConnectionError,
)

# --- Circuit breaker config -------------------------------------------------------
_CIRCUIT_BREAK_THRESHOLD = 4   # consecutive errors before opening
_CIRCUIT_BREAK_DURATION = 30.0  # seconds to stay open


class CircuitOpenError(Exception):
    """Raised when the HTTP circuit breaker is open (failing fast)."""
    pass


class Session:
    """
    requests.Session wrapper with:
    - Connection pooling (TCP reuse — fixes ConnectionResetError)
    - Retry with exponential backoff on transient errors
    - Circuit breaker: after N consecutive failures, fail-fast for 30s
    """

    def __init__(self, base_timeout: float = 30.0):
        self._session = requests.Session()
        self._base_timeout = base_timeout
        self._errors: list[float] = []   # timestamps of recent errors
        self._open = True

    def _is_circuit_broken(self) -> bool:
        """True when we're in a circuit-open state (failing fast)."""
        if not self._open:
            if time.time() - self._errors[-1] >= _CIRCUIT_BREAK_DURATION:
                self._open = True
                self._errors.clear()
                log.info("[http] Circuit breaker closed — resuming requests")
            else:
                return True
        return False

    def _record_error(self) -> None:
        self._errors.append(time.time())
        self._errors = self._errors[-(CIRCUIT_BREAK_THRESHOLD + 1):]

    def _check_circuit_and_raise(self) -> None:
        """Fail fast if circuit is open."""
        if self._open:
            return
        if time.time() - self._errors[-1] >= _CIRCUIT_BREAK_DURATION:
            self._open = True
            self._errors.clear()
            log.info("[http] Circuit breaker closed — resuming requests")
        else:
            raise CircuitOpenError("Circuit open")

    def _do_request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        headers: dict | None = None,
        timeout: float | None = None,
        verify: bool = False,
        retries: int = 3,
    ) -> requests.Response:
        """Shared retry loop for GET and POST. Cognitive complexity ≤ 12."""
        timeout = timeout or self._base_timeout
        for attempt in range(retries + 1):
            try:
                resp = self._session.request(
                    method, url,
                    params=params, json=json, headers=headers,
                    timeout=timeout, verify=verify,
                )
                if resp.status_code == 404:
                    return resp
                resp.raise_for_status()
                if self._errors:
                    self._errors.clear()
                return resp
            except _TRANSIENT_ERRORS as e:
                self._record_error()
                if len(self._errors) >= _CIRCUIT_BREAK_THRESHOLD:
                    self._open = False
                    log.warning(
                        f"[http] Circuit breaker opened — {len(self._errors)} consecutive errors, "
                        f"failing fast for {_CIRCUIT_BREAK_DURATION}s"
                    )
                    raise CircuitOpenError(
                        f"Circuit open after {len(self._errors)} consecutive errors"
                    )
                if attempt < retries:
                    wait = 2**attempt * 0.5
                    log.debug(
                        f"[http] Transient error ({e}), retry {attempt+1}/{retries} in {wait:.1f}s"
                    )
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError("unreachable")

    def get(self, url: str, *, params: dict | None = None, headers: dict | None = None,
            timeout: float | None = None, verify: bool = False,
            _retries: int = 3) -> requests.Response:
        """GET with session reuse, retry, and hard cap."""
        self._check_circuit_and_raise()
        return self._do_request("GET", url, params=params, headers=headers,
                                 timeout=timeout, verify=verify, retries=_retries)

    def post(self, url: str, *, json: dict | None = None, headers: dict | None = None,
             timeout: float | None = None, verify: bool = False,
             _retries: int = 3) -> requests.Response:
        """POST with session reuse, retry, and hard cap."""
        self._check_circuit_and_raise()
        return self._do_request("POST", url, json=json, headers=headers,
                                 timeout=timeout, verify=verify, retries=_retries)


# Module-level shared session (lazy — created on first use)
_session: Session | None = None


def get_session() -> Session:
    """Get or create the shared Session instance."""
    global _session
    if _session is None:
        _session = Session()
    return _session


def get(url: str, *, params: dict | None = None, headers: dict | None = None,
        timeout: float = 30.0, verify: bool = False) -> requests.Response:
    """GET with a hard wall-clock cap. Raises TimeoutError past the cap."""
    session = get_session()
    future = _POOL.submit(
        session.get, url, params=params, headers=headers,
        timeout=timeout, verify=verify, _retries=3,
    )
    try:
        return future.result(timeout=_HARD_CAP)
    except FutureTimeout as exc:
        future.cancel()
        raise TimeoutError(f"HTTP hard cap ({_HARD_CAP}s) exceeded: {url}") from exc


def post(url: str, *, json: dict | None = None, headers: dict | None = None,
          timeout: float = 30.0, verify: bool = False) -> requests.Response:
    """POST with a hard wall-clock cap. Raises TimeoutError past the cap."""
    session = get_session()
    future = _POOL.submit(
        session.post, url, json=json, headers=headers,
        timeout=timeout, verify=verify, _retries=3,
    )
    try:
        return future.result(timeout=_HARD_CAP)
    except FutureTimeout as exc:
        future.cancel()
        raise TimeoutError(f"HTTP hard cap ({_HARD_CAP}s) exceeded: {url}") from exc
