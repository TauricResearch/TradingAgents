"""HTTP helpers for AKShare calls on machines with a broken system proxy.

AKShare pulls A-share data from domestic hosts (e.g. eastmoney.com). When
Windows/macOS system proxy is enabled but the local proxy (often 127.0.0.1:7890)
is down, ``requests`` still routes through it and fails with ProxyError.
This module forces direct connections for AKShare HTTP calls only, retries
transient failures, and serializes concurrent requests to reduce rate limits.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, TypeVar

import requests

logger = logging.getLogger(__name__)

T = TypeVar("T")

_NO_PROXY = {"http": None, "https": None}
_RETRYABLE = (
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.Timeout,
    requests.exceptions.ProxyError,
)

_patch_lock = threading.Lock()
_fetch_lock = threading.Lock()
_patch_depth = 0
_original_session_request: Callable[..., requests.Response] | None = None


def _install_bypass_patch() -> None:
    global _original_session_request
    if _original_session_request is not None:
        return

    _original_session_request = requests.Session.request

    def _request(self, method, url, **kwargs):  # noqa: ANN001
        kwargs["proxies"] = _NO_PROXY
        saved_trust_env = self.trust_env
        self.trust_env = False
        try:
            return _original_session_request(self, method, url, **kwargs)  # type: ignore[misc]
        finally:
            self.trust_env = saved_trust_env

    requests.Session.request = _request  # type: ignore[method-assign]


def _remove_bypass_patch() -> None:
    global _original_session_request
    if _original_session_request is None:
        return
    requests.Session.request = _original_session_request  # type: ignore[method-assign]
    _original_session_request = None


@contextmanager
def bypass_system_proxy() -> Iterator[None]:
    """Thread-safe ref-counted patch for ``requests.Session.request``."""
    global _patch_depth
    with _patch_lock:
        if _patch_depth == 0:
            _install_bypass_patch()
        _patch_depth += 1
    try:
        yield
    finally:
        with _patch_lock:
            _patch_depth -= 1
            if _patch_depth == 0:
                _remove_bypass_patch()


def _should_bypass_proxy() -> bool:
    try:
        from tradingagents.dataflows.config import get_config

        return bool(get_config().get("akshare_bypass_system_proxy", True))
    except Exception:
        return True


def _retry_count() -> int:
    try:
        from tradingagents.dataflows.config import get_config

        return max(1, int(get_config().get("akshare_request_retries", 3)))
    except Exception:
        return 3


def _serialize_requests() -> bool:
    try:
        from tradingagents.dataflows.config import get_config

        return bool(get_config().get("akshare_request_serial", True))
    except Exception:
        return True


def run_akshare(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run an AKShare callable with proxy bypass, retries, and optional serialization."""
    attempts = _retry_count()
    use_bypass = _should_bypass_proxy()
    use_serial = _serialize_requests()
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            def _call() -> T:
                if use_bypass:
                    with bypass_system_proxy():
                        return func(*args, **kwargs)
                return func(*args, **kwargs)

            if use_serial:
                with _fetch_lock:
                    return _call()
            return _call()
        except _RETRYABLE as exc:
            last_error = exc
            if attempt + 1 >= attempts:
                break
            delay = 0.6 * (2**attempt)
            logger.warning(
                "AKShare request failed (%s), retry %s/%s in %.1fs",
                type(exc).__name__,
                attempt + 2,
                attempts,
                delay,
            )
            time.sleep(delay)

    assert last_error is not None
    raise last_error
