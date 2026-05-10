import threading
import time
from typing import Any, Dict, List, Union

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.messages import AIMessage


class StatsCallbackHandler(BaseCallbackHandler):
    """Callback handler that tracks LLM calls, tool calls, and token usage."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.llm_calls = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.role_stats: Dict[str, Dict[str, Union[int, float]]] = {}
        self._run_context: Dict[str, Dict[str, Union[str, float]]] = {}

    @staticmethod
    def _normalize_role(raw_role: str) -> str:
        role = (raw_role or "unknown").strip().lower().replace("-", " ")
        compact = " ".join(role.split())
        mapping = {
            "market analyst": "market_analyst",
            "social analyst": "social_media_analyst",
            "social media analyst": "social_media_analyst",
            "news analyst": "news_analyst",
            "fundamentals analyst": "fundamentals_analyst",
            "bull researcher": "bull_researcher",
            "bear researcher": "bear_researcher",
            "research manager": "research_manager",
            "trader": "trader",
            "aggressive analyst": "aggressive_analyst",
            "neutral analyst": "neutral_analyst",
            "conservative analyst": "conservative_analyst",
            "portfolio manager": "portfolio_manager",
        }
        return mapping.get(compact, compact.replace(" ", "_") or "unknown")

    @classmethod
    def _extract_role(
        cls,
        serialized: Dict[str, Any],
        **kwargs: Any,
    ) -> str:
        metadata = kwargs.get("metadata") or {}
        if isinstance(metadata, dict):
            for key in ("langgraph_node", "graph_node", "node", "node_name"):
                value = metadata.get(key)
                if isinstance(value, str) and value.strip():
                    return cls._normalize_role(value)

        tags = kwargs.get("tags") or []
        if isinstance(tags, list):
            for tag in tags:
                if not isinstance(tag, str):
                    continue
                if tag.startswith("role:"):
                    return cls._normalize_role(tag.split(":", 1)[1])

        name = serialized.get("name") if isinstance(serialized, dict) else None
        if isinstance(name, str) and name.strip():
            return cls._normalize_role(name)

        return "unknown"

    @staticmethod
    def _run_id_from_kwargs(**kwargs: Any) -> str:
        run_id = kwargs.get("run_id")
        return str(run_id) if run_id is not None else ""

    def _ensure_role_bucket(self, role: str) -> Dict[str, Union[int, float]]:
        if role not in self.role_stats:
            self.role_stats[role] = {
                "llm_calls": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "total_tokens": 0,
                "total_duration_seconds": 0.0,
            }
        return self.role_stats[role]

    def _register_start(self, serialized: Dict[str, Any], **kwargs: Any) -> None:
        role = self._extract_role(serialized, **kwargs)
        run_id = self._run_id_from_kwargs(**kwargs)
        started_at = time.perf_counter()

        with self._lock:
            self.llm_calls += 1
            role_bucket = self._ensure_role_bucket(role)
            role_bucket["llm_calls"] = int(role_bucket["llm_calls"]) + 1
            if run_id:
                self._run_context[run_id] = {
                    "role": role,
                    "started_at": started_at,
                }

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        **kwargs: Any,
    ) -> None:
        """Increment LLM call counter when an LLM starts."""
        self._register_start(serialized, **kwargs)

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        **kwargs: Any,
    ) -> None:
        """Increment LLM call counter when a chat model starts."""
        self._register_start(serialized, **kwargs)

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Extract token usage from LLM response."""
        try:
            generation = response.generations[0][0]
        except (IndexError, TypeError):
            return

        usage_metadata = None
        if hasattr(generation, "message"):
            message = generation.message
            if isinstance(message, AIMessage) and hasattr(message, "usage_metadata"):
                usage_metadata = message.usage_metadata

        run_id = self._run_id_from_kwargs(**kwargs)
        with self._lock:
            role = "unknown"
            duration = 0.0
            if run_id and run_id in self._run_context:
                ctx = self._run_context.pop(run_id)
                role = str(ctx.get("role") or "unknown")
                started_at = float(ctx.get("started_at") or 0.0)
                if started_at > 0.0:
                    duration = max(0.0, time.perf_counter() - started_at)

            role_bucket = self._ensure_role_bucket(role)
            role_bucket["total_duration_seconds"] = float(role_bucket["total_duration_seconds"]) + duration

            if usage_metadata:
                in_tokens = int(usage_metadata.get("input_tokens", 0) or 0)
                out_tokens = int(usage_metadata.get("output_tokens", 0) or 0)
                total_tokens = in_tokens + out_tokens

                self.tokens_in += in_tokens
                self.tokens_out += out_tokens

                role_bucket["tokens_in"] = int(role_bucket["tokens_in"]) + in_tokens
                role_bucket["tokens_out"] = int(role_bucket["tokens_out"]) + out_tokens
                role_bucket["total_tokens"] = int(role_bucket["total_tokens"]) + total_tokens

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        """Track duration for failed runs so latency averages stay representative."""
        run_id = self._run_id_from_kwargs(**kwargs)
        if not run_id:
            return
        with self._lock:
            ctx = self._run_context.pop(run_id, None)
            if not ctx:
                return
            role = str(ctx.get("role") or "unknown")
            started_at = float(ctx.get("started_at") or 0.0)
            duration = max(0.0, time.perf_counter() - started_at) if started_at > 0.0 else 0.0
            role_bucket = self._ensure_role_bucket(role)
            role_bucket["total_duration_seconds"] = float(role_bucket["total_duration_seconds"]) + duration

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        """Increment tool call counter when a tool starts."""
        with self._lock:
            self.tool_calls += 1

    def get_stats(self) -> Dict[str, Any]:
        """Return current statistics."""
        with self._lock:
            role_stats = {}
            for role, stats in self.role_stats.items():
                calls = int(stats.get("llm_calls", 0) or 0)
                duration = float(stats.get("total_duration_seconds", 0.0) or 0.0)
                role_stats[role] = {
                    "llm_calls": calls,
                    "tokens_in": int(stats.get("tokens_in", 0) or 0),
                    "tokens_out": int(stats.get("tokens_out", 0) or 0),
                    "total_tokens": int(stats.get("total_tokens", 0) or 0),
                    "total_duration_seconds": duration,
                    "avg_duration_seconds": (duration / calls) if calls else 0.0,
                }
            return {
                "llm_calls": self.llm_calls,
                "tool_calls": self.tool_calls,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
                "role_stats": role_stats,
            }
