"""Per-run trade-date clamp for tool wrappers.

Tool wrappers are exposed to LLMs as `@tool` callables. Their date params
are LLM-controlled, so without server-side enforcement the model can pass
end_date=today and read post-trade-date data. We bind the as-of trade_date
into a ContextVar at the start of each `propagate()` call and clamp every
LLM-supplied date in the tool wrapper to be no later than that.

ContextVar (rather than a closure or kwarg) is used because `ToolNode`s are
built once in `__init__` and shared across runs — the static graph topology
forbids per-run tool rebinding.
"""

from __future__ import annotations

import contextvars
import logging
from datetime import datetime
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_TRADE_DATE: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("tradingagents_trade_date", default=None)


def set_trade_date(trade_date: Optional[str]) -> contextvars.Token:
    """Set the as-of trade date for the current execution context.

    Call at the start of each `propagate()`; pair with `reset_trade_date`.
    """
    return _TRADE_DATE.set(trade_date)


def reset_trade_date(token: contextvars.Token) -> None:
    """Restore the prior trade-date contextvar value."""
    _TRADE_DATE.reset(token)


def get_trade_date() -> Optional[str]:
    """Return the current as-of trade date, or None if unset."""
    return _TRADE_DATE.get()


def clamp(date_str: Optional[str], param_label: str = "date") -> Tuple[Optional[str], bool]:
    """Clamp `date_str` to be no later than the contextvar trade_date.

    Returns `(clamped_value, was_clamped)`. Pass-through when:
      - no trade_date is set (e.g. running outside `propagate()` in a test)
      - the input is None or unparseable
      - the input is already <= trade_date
    """
    asof = _TRADE_DATE.get()
    if asof is None or not date_str:
        return date_str, False
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        a = datetime.strptime(asof, "%Y-%m-%d")
    except ValueError:
        return date_str, False
    if d > a:
        logger.warning(
            "tool date param %s=%s exceeds as-of trade_date %s; clamping",
            param_label,
            date_str,
            asof,
        )
        return asof, True
    return date_str, False


def maybe_note(was_clamped: bool, param_label: str) -> str:
    """Return a one-line tool-result prefix when a date was clamped, else ''."""
    if not was_clamped:
        return ""
    asof = _TRADE_DATE.get()
    return f"Note: {param_label} capped at as-of trade date {asof}.\n\n"
