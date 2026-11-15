"""LLM usage/cost meter and budget circuit breaker (RE.md 需求 5).

A ``UsageTracker`` is a LangChain callback handler that aggregates the
prompt/completion tokens of every LLM call in a run, estimates USD from the
price table in ``model_catalog``, and — when a per-run budget is set — stops
the run *before* the next model request goes out.

Design notes
------------
* One tracker per run, shared by the graph and the CLI. Two runs never share
  totals or stop state.
* Events are de-duplicated by ``run_id``: a retry or a stream can fire the same
  start/end twice for one call, and it must be counted once.
* The budget is checked before a call is dispatched (``spent >= budget``). Token
  usage is only known when a call ends, so an in-flight request can push the
  running total past the cap; that completion is still counted (accurate
  accounting beats a perfectly bounded total).
* Budget stopping relies on ``raise_error=True``: raising from
  ``on_chat_model_start`` / ``on_llm_start`` makes LangChain abort the call
  before the underlying provider request is issued.
* Prices are never invented. A ``(provider, model)`` with no price row is
  reported as unknown and adds nothing to the total; only a call *confirmed*
  free (price 0) contributes 0.0. Local endpoints (ollama, openai_compatible)
  are unknown unless the table says otherwise.
"""

from __future__ import annotations

import math
import threading
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from .model_catalog import get_price


class BudgetExceeded(RuntimeError):
    """Raised when a run would exceed ``max_run_budget_usd``; aborts the run."""


def _parse_budget(value: Any) -> float | None:
    """Validate a budget value to a finite non-negative float, or ``None``.

    ``None`` means no cap and is left as is (not coerced). A numeric string is
    accepted (env vars arrive as strings). Booleans, non-numeric strings, NaN,
    ±inf and negatives are rejected loudly so a misconfiguration fails at
    startup rather than silently disabling the cap.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"max_run_budget_usd must be a number, not a boolean: {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"max_run_budget_usd must be a number, got {value!r}") from exc
    if math.isnan(number) or math.isinf(number):
        raise ValueError(f"max_run_budget_usd must be finite, got {value!r}")
    if number < 0:
        raise ValueError(f"max_run_budget_usd must be >= 0, got {number}")
    return number


def estimate_cost(provider: str | None, model: str | None,
                  input_tokens: int, output_tokens: int) -> float | None:
    """USD for one call, or ``None`` when the model's price is unknown."""
    price = get_price(provider, model)
    if price is None:
        return None
    in_per_m, out_per_m = price
    return (input_tokens / 1_000_000) * in_per_m + (output_tokens / 1_000_000) * out_per_m


class UsageTracker(BaseCallbackHandler):
    """Aggregate per-run LLM usage and enforce an optional USD budget."""

    # A handler error must abort the call, not be swallowed by the callback
    # manager; this is what lets the budget stop the run before a request.
    raise_error = True

    def __init__(self, budget_usd: Any = None) -> None:
        super().__init__()
        self.budget_usd: float | None = _parse_budget(budget_usd)
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        """Clear all counters and stop state, for the next run on a reused graph.

        The same handler instance stays wired into the models' callbacks; a
        reset gives each run its own meter, so a reused graph never inherits the
        previous run's spend or its budget stop.
        """
        with getattr(self, "_lock", threading.Lock()):
            self.stopped = False
            self.stop_reason: str | None = None
            self._starts: set[str] = set()       # run_ids whose start was counted
            self._ends: set[str] = set()         # run_ids whose end was counted
            self._in_flight: dict[str, tuple[str | None, str | None]] = {}
            self.calls = 0
            self.tokens_in = 0
            self.tokens_out = 0
            self.total_usd = 0.0
            # Calls whose response carried no usage_metadata: their cost is
            # unknown, not zero, so the summary is flagged incomplete.
            self.missing_usage_calls = 0
            self.unknown_models: set[tuple[str, str]] = set()
            self.by_model: dict[tuple[str, str], dict[str, Any]] = {}

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _model_key(serialized: dict | None, metadata: dict | None) -> tuple[str | None, str | None]:
        """The (provider, model) of a call: tier metadata first, then serialized."""
        metadata = metadata or {}
        provider = metadata.get("ta_provider")
        model = metadata.get("ta_model")
        kwargs = (serialized or {}).get("kwargs") or {}
        model = model or kwargs.get("model_name") or kwargs.get("model")
        return provider, model

    def _run_id(self, kwargs: dict) -> str:
        run_id = kwargs.get("run_id")
        return str(run_id) if run_id is not None else ""

    # -- start: count once, enforce budget --------------------------------
    def _on_start(self, serialized: dict, metadata: dict | None, kwargs: dict) -> None:
        provider, model = self._model_key(serialized, metadata)
        run_id = self._run_id(kwargs)
        with self._lock:
            if run_id and run_id in self._starts:
                return   # duplicate start for this call
            # A call confirmed free (price 0 for both directions) never spends, so
            # it must never trip the cap — even a 0 budget lets it through.
            confirmed_free = get_price(provider, model) == (0.0, 0.0)
            if (not confirmed_free and self.budget_usd is not None
                    and self.total_usd >= self.budget_usd):
                self.stopped = True
                self.stop_reason = "BUDGET_STOPPED"
                raise BudgetExceeded(
                    f"Run budget of ${self.budget_usd:.4f} reached "
                    f"(spent ${self.total_usd:.4f}); refusing further requests."
                )
            if run_id:
                self._starts.add(run_id)
            self._in_flight[run_id] = (provider, model)

    def on_chat_model_start(self, serialized, messages, **kwargs) -> None:
        self._on_start(serialized, kwargs.get("metadata"), kwargs)

    def on_llm_start(self, serialized, prompts, **kwargs) -> None:
        self._on_start(serialized, kwargs.get("metadata"), kwargs)

    # -- end: aggregate once, even for an in-flight call after a stop -----
    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        run_id = self._run_id(kwargs)
        # A call that was started but never counted (or a stopped one whose end
        # still arrives) must not be dropped; fall back to metadata/serialized.
        with self._lock:
            if run_id and run_id in self._ends:
                return   # duplicate end for this call
            provider, model = self._in_flight.pop(run_id, (None, None))
            if provider is None and model is None:
                provider, model = self._model_key(None, kwargs.get("metadata"))
            if run_id:
                self._ends.add(run_id)
            if not (run_id and run_id in self._starts):
                # an end without a counted start still is a real call
                self._starts.add(run_id)
            in_tokens, out_tokens, has_usage = self._usage(response)
            self.calls += 1
            self.tokens_in += in_tokens
            self.tokens_out += out_tokens
            if not has_usage:
                # The provider reported no token usage: the cost is unknown, not
                # zero. Record the gap so the summary is not read as a known $0.
                self.missing_usage_calls += 1
            cost = estimate_cost(provider, model, in_tokens, out_tokens)
            key = (str(provider), str(model))
            bucket = self.by_model.setdefault(
                key, {"calls": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0.0, "known": cost is not None})
            bucket["calls"] += 1
            bucket["tokens_in"] += in_tokens
            bucket["tokens_out"] += out_tokens
            if cost is None:
                self.unknown_models.add(key)
            else:
                self.total_usd += cost
                bucket["usd"] += cost

    def on_llm_error(self, error: BaseException, **kwargs) -> None:
        run_id = self._run_id(kwargs)
        with self._lock:
            self._in_flight.pop(run_id, None)

    @staticmethod
    def _usage(response: LLMResult) -> tuple[int, int, bool]:
        """(input, output, has_usage) from the first generation's usage_metadata.

        ``has_usage`` is False when the generation carries no ``usage_metadata``
        at all — distinct from a call that reported zero tokens.
        """
        try:
            generation = response.generations[0][0]
        except (IndexError, TypeError):
            return 0, 0, False
        message = getattr(generation, "message", None)
        usage = getattr(message, "usage_metadata", None)
        if not usage:
            return 0, 0, False
        return int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0), True

    # -- summary -----------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """A JSON-serializable summary of the run's usage and budget state."""
        with self._lock:
            return {
                "calls": self.calls,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
                "total_usd": round(self.total_usd, 6),
                "missing_usage_calls": self.missing_usage_calls,
                # False when any call omitted usage: tokens/cost are a lower
                # bound, not a known total.
                "usage_complete": self.missing_usage_calls == 0,
                "budget_usd": self.budget_usd,
                "stopped": self.stopped,
                "stop_reason": self.stop_reason,
                "unknown_models": sorted(self.unknown_models),
                "by_model": {
                    f"{provider}/{model}": dict(bucket)
                    for (provider, model), bucket in sorted(self.by_model.items())
                },
            }
