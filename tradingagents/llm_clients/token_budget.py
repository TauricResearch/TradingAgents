"""A token budget for one run that stops it before it spends past the limit (#515).

``max_tool_rounds`` bounds one analyst's tool loop (#1420), but nothing bounded
what a whole run spends: every analyst, debater, manager and memory reflection
draws on the same provider bill. ``TokenBudgetHandler`` keeps one total across
all of them and refuses the next model call once the total reaches the budget.

What counts: ``usage_metadata["input_tokens"] + ["output_tokens"]`` per call.
``input_tokens`` is the whole prompt sent on that call (history and tool results
included), with cache reads and writes folded in by the LangChain provider
packages; ``output_tokens`` includes reasoning/thinking tokens. Every token
counts the same, so with heavy prompt caching the budget overstates cost.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


class TokenBudgetExceeded(RuntimeError):
    """The run reached its ``run_token_budget``; no further model call is made."""

    def __init__(self, spent: int, budget: int) -> None:
        self.spent = spent
        self.budget = budget
        super().__init__(
            f"Token budget exhausted: {spent:,} of {budget:,} tokens used "
            "(run_token_budget / TRADINGAGENTS_RUN_TOKEN_BUDGET)"
        )


def _coerce_run_token_budget(value):
    """Validate a ``run_token_budget`` value to a positive int (env vars are strings)."""
    if isinstance(value, bool):
        raise ValueError(f"run_token_budget must be an integer, not a boolean: {value!r}")
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"run_token_budget must be an integer, got {value!r}") from exc
    if n <= 0:
        raise ValueError(f"run_token_budget must be > 0, got {n}")
    return n


class TokenBudgetHandler(BaseCallbackHandler):
    """Count tokens across a run and raise before a call once the budget is spent.

    Analysts run in parallel, so calls already in flight when the total crosses
    the budget still finish: a run can overshoot by about one call per analyst.
    A provider SDK's own retries happen inside one start/end pair and tokens
    are counted only from a finished call, so a retry never counts twice.
    """

    # Without this LangChain logs an exception raised in a callback and carries
    # on. It is honoured for sync handlers only: an AsyncCallbackHandler's error
    # is swallowed on the sync path, so keep this handler synchronous.
    raise_error = True

    def __init__(self, budget: int) -> None:
        self.budget = budget
        self._lock = threading.Lock()
        self.spent = 0
        self._warned_no_usage = False

    def reset(self) -> None:
        """Start a new run from zero."""
        with self._lock:
            self.spent = 0
            self._warned_no_usage = False

    def remaining(self) -> int:
        with self._lock:
            return max(self.budget - self.spent, 0)

    def _check(self) -> None:
        with self._lock:
            spent = self.spent
        if spent >= self.budget:
            raise TokenBudgetExceeded(spent, self.budget)

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        self._check()

    def on_chat_model_start(self, serialized: dict[str, Any], messages: list[list[Any]], **kwargs: Any) -> None:
        self._check()

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        used = 0
        for generations in response.generations:
            for generation in generations:
                usage = getattr(getattr(generation, "message", None), "usage_metadata", None)
                if usage:
                    used += (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)
        with self._lock:
            if used:
                self.spent += used
                return
            warn = not self._warned_no_usage
            self._warned_no_usage = True
        if warn:
            logger.warning(
                "A model call reported no token usage; run_token_budget cannot count it."
            )
