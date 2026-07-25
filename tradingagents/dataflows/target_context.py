"""Process-local target ticker context for tool-layer identity guards.

The analysis target ticker is resolved once at graph run start and stored
here so stateless ``@tool`` functions can read it without being passed the
LangGraph state. Tools compare the requested ticker against this target to
inject a comparison-ticker notice when an agent queries a different symbol
(e.g. for contrast analysis), preventing accidental data mixing across
tickers in multi-round debate.

The context is a ``ContextVar`` so it propagates within the executing thread
for the duration of one run. ``TradingAgentsGraph.resolve_instrument_context``
sets it at run start and ``AnalysisRunner.run`` clears it in its finally
block. When unset (bare programmatic states, tests), the guard is a no-op.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass


@dataclass(frozen=True)
class TargetTicker:
    ticker: str
    company_name: str | None


_target_ticker: contextvars.ContextVar[TargetTicker | None] = contextvars.ContextVar(
    "tradingagents_target_ticker", default=None
)


def set_target_ticker(ticker: str, company_name: str | None = None) -> None:
    """Set the analysis target ticker for the current run context."""
    _target_ticker.set(TargetTicker(ticker=str(ticker), company_name=company_name))


def get_target_ticker() -> TargetTicker | None:
    """Return the current run's target ticker, or None when unset."""
    return _target_ticker.get()


def clear_target_ticker() -> None:
    """Clear the target ticker at run end."""
    _target_ticker.set(None)
