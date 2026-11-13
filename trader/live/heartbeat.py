"""The live account's heartbeat (ADR 0010): after each hourly run that returns, one GET
of the address an outside monitoring service gave for it. The machine's alerts are
sent from the machine, and none goes out when the run does not happen; the service
tells the user when two hours pass without a beat.

Whoever has the address can beat in the run's place, so it stays out of the logs:
they name its host at most.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10


def beat(url: str | None, get: Callable[..., requests.Response] = requests.get) -> bool:
    """GET ``url``; True when the service took it, nothing without a ``url``. Never
    raises: a missed beat is the service's to report, not a failure of the run."""
    if not url:
        return False
    host = urlsplit(url).hostname or "?"
    try:
        get(url, timeout=TIMEOUT_SECONDS).raise_for_status()
    except Exception as exc:  # its message may carry the address, so it is not logged
        status = getattr(getattr(exc, "response", None), "status_code", None)
        logger.error("heartbeat to %s failed: %s %s", host, type(exc).__name__, status or "")
        return False
    logger.info("heartbeat sent to %s", host)
    return True
