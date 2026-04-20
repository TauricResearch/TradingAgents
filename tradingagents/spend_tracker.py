"""LangChain callback handler that tracks cumulative token usage and cost."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class BudgetExceededError(Exception):
    """Raised when the spend budget is exceeded mid-graph."""
    pass


@dataclass
class AuditEntry:
    """Single entry in the delegation chain audit trail."""

    agent: str
    call_type: str  # "llm" or "tool"
    name: str  # model name or tool name
    cost_usd: float
    prompt_tokens: int
    completion_tokens: int
    timestamp: float = field(default_factory=time.monotonic)

# Pricing per 1M tokens: (input_usd, output_usd)
# Source: provider pricing pages as of 2025-Q2. Add new models as needed.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    # Anthropic
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-opus-20240229": (15.00, 75.00),
    # Google
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
}

# Fallback: generous estimate so unknown models still get a cost ceiling
_DEFAULT_PRICING: tuple[float, float] = (10.00, 30.00)


def _get_pricing(model: str) -> tuple[float, float]:
    """Return (input_per_1M, output_per_1M) for *model*, with prefix matching."""
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    # Try prefix match (e.g. "gpt-4o-2024-08-06" → "gpt-4o")
    for key in sorted(MODEL_PRICING, key=len, reverse=True):
        if model.startswith(key):
            return MODEL_PRICING[key]
    return _DEFAULT_PRICING


@dataclass
class TokenRecord:
    """Single LLM call token record."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class SpendTracker(BaseCallbackHandler):
    """Tracks cumulative token usage and estimated USD cost.

    Thread-safe: LangGraph may invoke nodes concurrently.

    Args:
        max_cost: Optional USD budget. When exceeded, ``budget_exceeded``
                  becomes ``True``. Callers should check this flag and abort.

    Usage::

        tracker = SpendTracker(max_cost=0.50)
        graph = TradingAgentsGraph(callbacks=[tracker])
        # ... run graph ...
        print(tracker.total_cost_usd)
        print(tracker.budget_exceeded)
    """

    def __init__(self, max_cost: float | None = None) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0
        self.total_cost_usd: float = 0.0
        self.max_cost: float | None = max_cost
        self.budget_exceeded: bool = False
        self.records: list[TokenRecord] = []
        # Per-ticker spend tracking
        self.ticker_costs: dict[str, float] = {}
        self._ticker_snapshot: float = 0.0  # cumulative cost at last ticker start
        # Delegation chain audit trail
        self.audit_trail: list[AuditEntry] = []
        self._run_names: dict[UUID, str] = {}  # run_id → chain/agent name
        self._run_parents: dict[UUID, UUID] = {}  # run_id → parent_run_id
        self._tool_starts: dict[UUID, str] = {}  # run_id → tool name

    # -- LangChain callback hooks ------------------------------------------

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Track chain/agent names for the delegation audit trail."""
        name = serialized.get("name") or serialized.get("id", [""])[-1] or ""
        with self._lock:
            if name:
                self._run_names[run_id] = name
            if parent_run_id is not None:
                self._run_parents[run_id] = parent_run_id

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Abort before the next LLM call if budget already exceeded."""
        with self._lock:
            if parent_run_id is not None:
                self._run_parents[run_id] = parent_run_id
            if self.budget_exceeded:
                raise BudgetExceededError(
                    f"Budget ${self.max_cost:.2f} exceeded (spent ${self.total_cost_usd:.4f})"
                )

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Abort before the next chat model call if budget already exceeded."""
        with self._lock:
            if parent_run_id is not None:
                self._run_parents[run_id] = parent_run_id
            if self.budget_exceeded:
                raise BudgetExceededError(
                    f"Budget ${self.max_cost:.2f} exceeded (spent ${self.total_cost_usd:.4f})"
                )

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Record tool invocation start for audit trail."""
        tool_name = serialized.get("name") or "unknown_tool"
        with self._lock:
            self._tool_starts[run_id] = tool_name
            if parent_run_id is not None:
                self._run_parents[run_id] = parent_run_id

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Record completed tool call in audit trail."""
        with self._lock:
            tool_name = self._tool_starts.pop(run_id, "unknown_tool")
            agent = self._resolve_agent(parent_run_id or run_id)
            self.audit_trail.append(
                AuditEntry(
                    agent=agent,
                    call_type="tool",
                    name=tool_name,
                    cost_usd=0.0,
                    prompt_tokens=0,
                    completion_tokens=0,
                )
            )

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        usage = self._extract_usage(response)
        if usage is None:
            return
        prompt, completion, total = usage
        model = self._extract_model(response)
        inp_price, out_price = _get_pricing(model)
        call_cost = (prompt * inp_price + completion * out_price) / 1_000_000

        with self._lock:
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            self.total_tokens += total
            self.total_cost_usd += call_cost
            self.records.append(
                TokenRecord(
                    model=model,
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    total_tokens=total,
                )
            )
            # Audit trail: resolve which agent triggered this LLM call
            agent = self._resolve_agent(parent_run_id or run_id)
            self.audit_trail.append(
                AuditEntry(
                    agent=agent,
                    call_type="llm",
                    name=model,
                    cost_usd=call_cost,
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                )
            )
            if self.max_cost is not None and self.total_cost_usd >= self.max_cost:
                self.budget_exceeded = True

    # -- helpers -----------------------------------------------------------

    def _resolve_agent(self, run_id: UUID | None) -> str:
        """Walk the parent chain to find the nearest named agent/chain. Must hold _lock."""
        visited: set[UUID] = set()
        current = run_id
        while current and current not in visited:
            visited.add(current)
            name = self._run_names.get(current)
            if name:
                return name
            current = self._run_parents.get(current)
        return "unknown"

    @staticmethod
    def _extract_usage(response: LLMResult) -> tuple[int, int, int] | None:
        """Pull token counts from LLMResult.llm_output or generation metadata."""
        # Most providers put token_usage in llm_output
        llm_out = response.llm_output or {}
        usage = llm_out.get("token_usage") or llm_out.get("usage") or {}
        if usage:
            prompt = usage.get("prompt_tokens", 0) or 0
            completion = usage.get("completion_tokens", 0) or 0
            total = usage.get("total_tokens", 0) or (prompt + completion)
            return prompt, completion, total

        # Fallback: check generation-level response_metadata (langchain-openai ≥0.3)
        for gen_list in response.generations:
            for gen in gen_list:
                meta = getattr(gen, "generation_info", None) or {}
                usage = meta.get("usage") or meta.get("token_usage") or {}
                if usage:
                    prompt = usage.get("prompt_tokens", 0) or 0
                    completion = usage.get("completion_tokens", 0) or 0
                    total = usage.get("total_tokens", 0) or (prompt + completion)
                    return prompt, completion, total

        return None

    @staticmethod
    def _extract_model(response: LLMResult) -> str:
        llm_out = response.llm_output or {}
        return llm_out.get("model_name", "") or llm_out.get("model", "unknown")

    def begin_ticker(self, ticker: str) -> None:
        """Mark the start of a new ticker analysis. Call before propagate()."""
        with self._lock:
            self._ticker_snapshot = self.total_cost_usd

    def log_ticker_spend(self, ticker: str) -> None:
        """Log per-ticker and cumulative spend to stderr. Call after propagate()."""
        print(self.format_ticker_spend(ticker), file=sys.stderr)

    def format_ticker_spend(self, ticker: str) -> str:
        """Return a human-readable ticker spend string."""
        with self._lock:
            ticker_cost = self.total_cost_usd - self._ticker_snapshot
            self.ticker_costs[ticker] = self.ticker_costs.get(ticker, 0.0) + ticker_cost
            budget_str = f" / budget ${self.max_cost:.2f}" if self.max_cost is not None else ""
            exceeded = " [OVER BUDGET]" if self.budget_exceeded else ""
            return f"[spend] {ticker}: ${ticker_cost:.4f} | cumulative: ${self.total_cost_usd:.4f}{budget_str}{exceeded}"

    def reset(self) -> None:
        """Reset all counters."""
        with self._lock:
            self.prompt_tokens = 0
            self.completion_tokens = 0
            self.total_tokens = 0
            self.total_cost_usd = 0.0
            self.budget_exceeded = False
            self.records.clear()
            self.audit_trail.clear()
            self._run_names.clear()
            self._run_parents.clear()
            self._tool_starts.clear()

    def format_audit_trail(self) -> str:
        """Return a human-readable audit trail string."""
        with self._lock:
            if not self.audit_trail:
                return "[audit] No calls recorded."
            lines = ["[audit] Delegation chain:"]
            for i, e in enumerate(self.audit_trail, 1):
                if e.call_type == "llm":
                    lines.append(
                        f"  {i}. {e.agent} → LLM({e.name}) "
                        f"tokens={e.prompt_tokens}+{e.completion_tokens} "
                        f"cost=${e.cost_usd:.4f}"
                    )
                else:
                    lines.append(f"  {i}. {e.agent} → tool({e.name})")
            return "\n".join(lines)

    def log_audit_trail(self) -> None:
        """Print the audit trail to stderr."""
        print(self.format_audit_trail(), file=sys.stderr)
