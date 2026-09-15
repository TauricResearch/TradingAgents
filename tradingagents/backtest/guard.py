"""Assert that a historical run never reaches for data past its as-of date.

The framework has fixed look-ahead in several places — FRED vintage pinning
(#1275), the shared UTC social/news window (#1220), the decision log's
resolution-date gate (#1251), indicator cutoffs — but until now each fix was
verified only by its own unit test. Nothing checked the property end to end, so
a new vendor or a refactor could reintroduce leakage silently and the only
symptom would be a backtest that looks too good.

This module closes that gap. Every data request passes through
``route_to_vendor``, so a guard installed there sees all of them. Any date
argument later than the run's as-of date is a request for information that did
not exist yet, and the guard raises.

The check is intentionally structure-agnostic: rather than encoding each
vendor method's signature (which would rot the moment a new one lands), it
scans every argument for anything shaped like a date and compares it. A new
vendor method is covered the day it is added, without touching this file.

The dispatch hook is a single process-wide slot, but the as-of date it checks
against is thread-local, so a backtest running several tickers concurrently
holds each thread to its own trade date rather than to whichever one was
installed last.

Usage::

    with point_in_time_guard("2026-01-05"):
        graph.propagate("NVDA", "2026-01-05")
"""

from __future__ import annotations

import logging
import re
import threading
from contextlib import contextmanager

from tradingagents.dataflows.interface import set_request_guard

logger = logging.getLogger(__name__)

# ISO dates anywhere in a string argument. Vendor calls pass dates as plain
# yyyy-mm-dd throughout the codebase, so this catches them without needing to
# know which positional slot each method puts them in.
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

# Per-thread guard settings. A thread with no ``as_of`` set is unguarded, so
# installing the hook never affects unrelated work sharing the process.
_local = threading.local()

# The hook occupies one process-wide slot, so nested or concurrent guards share
# a single installation and the last one out restores what was there before.
_install_lock = threading.Lock()
_install_count = 0
_previous_guard = None


class LookAheadError(AssertionError):
    """Raised when a historical run requests data from after its as-of date."""


def _dates_in(value: object) -> list[str]:
    """Every ISO date found in ``value``, recursing into containers."""
    if isinstance(value, str):
        return _DATE_RE.findall(value)
    if isinstance(value, dict):
        return [d for v in value.values() for d in _dates_in(v)]
    if isinstance(value, (list, tuple, set)):
        return [d for v in value for d in _dates_in(v)]
    return []


def check_request(method: str, args: tuple, kwargs: dict, as_of: str) -> None:
    """Raise :class:`LookAheadError` if any date argument is past ``as_of``.

    A date equal to ``as_of`` is allowed: the analysis window is inclusive of
    the trade date, which is the framework's existing convention.
    """
    found = _dates_in(args) + _dates_in(kwargs)
    future = sorted({d for d in found if d > as_of})
    if future:
        raise LookAheadError(
            f"{method} requested data dated {', '.join(future)} during a run "
            f"as of {as_of}. A historical run must not see dates after its "
            f"trade date — this is the look-ahead guard (#1220/#1251/#1275)."
        )


def _dispatch_guard(method, args, kwargs):
    """The installed hook: applies whatever settings this thread has, if any."""
    as_of = getattr(_local, "as_of", None)
    if as_of is None:
        return
    try:
        check_request(method, args, kwargs, as_of)
    except LookAheadError as exc:
        if getattr(_local, "strict", True):
            raise
        _local.violations.append(str(exc))
        logger.warning("Point-in-time violation (non-strict): %s", exc)


def _install() -> None:
    global _install_count, _previous_guard
    with _install_lock:
        if _install_count == 0:
            _previous_guard = set_request_guard(_dispatch_guard)
        _install_count += 1


def _uninstall() -> None:
    global _install_count, _previous_guard
    with _install_lock:
        _install_count -= 1
        if _install_count == 0:
            set_request_guard(_previous_guard)
            _previous_guard = None


@contextmanager
def point_in_time_guard(as_of: str, strict: bool = True):
    """Enforce (or, with ``strict=False``, just report) the point-in-time rule.

    Args:
        as_of: The run's trade date (``yyyy-mm-dd``). Requests for later dates
            are violations.
        strict: When ``True`` a violation raises and the decision is recorded
            as a failure. When ``False`` violations are logged and collected but
            the run continues — useful for surveying an existing setup, or for a
            vendor whose own API echoes a later date back in an argument.

    Yields:
        A list that accumulates violation messages. It stays empty under
        ``strict=True`` because the first violation raises.
    """
    violations: list[str] = []
    previous = (
        getattr(_local, "as_of", None),
        getattr(_local, "strict", True),
        getattr(_local, "violations", None),
    )
    _local.as_of = as_of
    _local.strict = strict
    _local.violations = violations

    _install()
    try:
        yield violations
    finally:
        _uninstall()
        _local.as_of, _local.strict, _local.violations = previous
