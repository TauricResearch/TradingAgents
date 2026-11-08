"""Cooperative per-decision deadline guard (fork audit R3, 2026-11-09).

The /decide caller (news-gap-ml's live_listener) gives up after
DECIDE_TIMEOUT_SEC=600s -- but nothing stopped the graph server-side:
uvicorn ran run_decision() to completion after the client disconnected,
and the rest of the decision's LLM calls kept billing (observed live on
2026-09-10: six-plus consecutive 600s timeouts, each still spending).
scripts/service.py now passes a deadline just under the caller's timeout;
wrapping the graph's two shared LLM runnables makes every invoke past
that deadline raise DeadlineExceeded *before* the billed call. The
in-flight call finishes (unavoidable), everything after it never happens,
and the chain unwinds through LangGraph's normal node-error channel.

Why a Runnable wrapper and not a LangChain callback handler: the default
callback manager swallows handler exceptions (raise_error=False), so an
on_llm_start that raises would be logged and the billed call would still
proceed. A Runnable sitting in the call path raises through the same
error channel as a provider failure, which propagate() lets surface.

The wrapper must satisfy every way the agents touch an LLM (grep
tradingagents/agents for the authoritative list):
  * llm.invoke(...)                          -- researchers, risk debaters,
                                                portfolio manager, Reflector
  * (prompt | llm).invoke(...)               -- analyst wrap-up turn
  * (prompt | llm.bind_tools(t)).invoke()    -- analyst tool turns
  * llm.with_structured_output(schema)       -- structured-mode extraction
Anything else (model_name and friends) passes through via __getattr__.
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import Runnable


class DeadlineExceeded(TimeoutError):
    """A decision's server-side deadline passed; raised before the next
    billed LLM call so a runaway chain stops spending. Subclasses
    TimeoutError so callers scanning for timeout-class failures still
    recognise it."""


class DeadlineGuardedRunnable(Runnable):
    """Wraps one of the graph's shared LLM runnables so any invoke after
    ``deadline_monotonic`` raises DeadlineExceeded instead of spending.

    The two tier LLMs are created once per decision in TradingAgentsGraph
    and shared by every agent, so wrapping them here covers the whole
    graph without touching a single agent. bind_tools() /
    with_structured_output() re-wrap their result so the guard survives
    into the bound runnable the analyst chains actually invoke.
    """

    def __init__(self, inner: Any, deadline_monotonic: float, label: str = ""):
        self._inner = inner
        self._deadline = deadline_monotonic
        self._label = label or type(inner).__name__

    def _check_deadline(self) -> None:
        overrun = time.monotonic() - self._deadline
        if overrun > 0:
            raise DeadlineExceeded(
                f"decision deadline passed {overrun:.1f}s ago (before the next "
                f"{self._label} call); stopping the chain rather than billing further"
            )

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        self._check_deadline()
        return self._inner.invoke(input, config, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> DeadlineGuardedRunnable:
        return type(self)(self._inner.bind_tools(tools, **kwargs), self._deadline, self._label)

    def with_structured_output(self, schema: Any, **kwargs: Any) -> DeadlineGuardedRunnable:
        return type(self)(self._inner.with_structured_output(schema, **kwargs), self._deadline, self._label)

    def __getattr__(self, name: str) -> Any:
        # Only fires for attributes NOT on the wrapper itself (model_name,
        # provider metadata, capability probes). Guard against __init__
        # not having run yet (copy/pickle probes) so those get a clean
        # AttributeError instead of a KeyError.
        try:
            inner = self.__dict__["_inner"]
        except KeyError:
            raise AttributeError(name) from None
        return getattr(inner, name)
