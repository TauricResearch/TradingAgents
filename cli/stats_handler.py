import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)


def _extract_fingerprint(response: LLMResult) -> Dict[str, Optional[str]]:
    """Best-effort extraction of model identity + fingerprint from an LLM result.

    Returns ``{"model": str|None, "fingerprint": str|None}``. We look in a few
    places because LangChain exposes provider metadata inconsistently:
    - ``response.llm_output`` is the OpenAI Chat-Completions convention and
      carries ``system_fingerprint`` directly.
    - ``generation.generation_info`` is used by some providers (incl. OpenAI
      Responses API; Anthropic surfaces the model id here as ``model``).
    - ``message.response_metadata`` is the modern home for both fields on
      chat-model providers.

    The presence/absence of ``fingerprint`` is itself audit signal — record it
    even when None, so downstream drift detection (T3.4) can distinguish
    "provider didn't return one" from "we forgot to look".
    """
    model: Optional[str] = None
    fingerprint: Optional[str] = None

    llm_output = getattr(response, "llm_output", None)
    if isinstance(llm_output, dict):
        model = model or llm_output.get("model_name") or llm_output.get("model")
        fingerprint = fingerprint or llm_output.get("system_fingerprint")

    try:
        generation = response.generations[0][0]
    except (IndexError, TypeError, AttributeError):
        generation = None

    if generation is not None:
        gen_info = getattr(generation, "generation_info", None) or {}
        if isinstance(gen_info, dict):
            model = model or gen_info.get("model_name") or gen_info.get("model")
            fingerprint = fingerprint or gen_info.get("system_fingerprint")

        message = getattr(generation, "message", None)
        meta = getattr(message, "response_metadata", None) or {}
        if isinstance(meta, dict):
            model = model or meta.get("model_name") or meta.get("model")
            fingerprint = fingerprint or meta.get("system_fingerprint")

    return {"model": model, "fingerprint": fingerprint}


class StatsCallbackHandler(BaseCallbackHandler):
    """Callback handler that tracks LLM calls, tool calls, and token usage.

    T0.5 — when ``jsonl_path`` is provided, every LLM call ends produces one
    appended line in that file, giving a per-call structured audit log
    that's the on-disk ancestor of the full TraceCallback in Phase 1.
    The in-memory counters and ``fingerprints`` list still work the way
    they did pre-T0.5, so existing CLI display code is unaffected.
    """

    def __init__(
        self,
        *,
        jsonl_path: Optional[Union[str, Path]] = None,
        session_id: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.llm_calls = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        # T0.2 — per-call identity record. Each entry is one LLM call
        # observed by on_llm_end, in invocation order. Format matches what
        # the future TraceCallback (T1.2) will emit, so downstream code can
        # consume either source uniformly.
        self.fingerprints: List[Dict[str, Optional[str]]] = []

        # T0.5 — JSONL persistence. Disabled iff jsonl_path is None, which
        # keeps the in-process default behavior bit-identical to pre-T0.5
        # for callers that haven't opted in.
        self.session_id: str = session_id or str(uuid.uuid4())
        self.jsonl_path: Optional[Path] = (
            Path(jsonl_path).expanduser() if jsonl_path else None
        )
        if self.jsonl_path is not None:
            # Materialise the directory eagerly; an explicit mkdir failure
            # at handler construction is clearer than a silent on_llm_end
            # write failure ten seconds into a 5-minute trade analysis.
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)

        # Per-call latency tracking. Keyed by LangChain's per-call ``run_id``
        # so the start→end pairing survives async / parallel chat-model
        # calls. Cleaned up on on_llm_end so the dict never grows unbounded.
        self._start_times: Dict[str, float] = {}
        self._call_seq = 0

    # ------------------------------------------------------------------ #
    # LangChain callback hooks
    # ------------------------------------------------------------------ #

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        run_id: Optional[uuid.UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Increment LLM call counter when an LLM starts."""
        with self._lock:
            self.llm_calls += 1
            if run_id is not None:
                self._start_times[str(run_id)] = time.monotonic()

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        run_id: Optional[uuid.UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Increment LLM call counter when a chat model starts."""
        with self._lock:
            self.llm_calls += 1
            if run_id is not None:
                self._start_times[str(run_id)] = time.monotonic()

    def on_llm_end(
        self,
        response: LLMResult,
        run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Extract token usage, fingerprint, and write a per-call JSONL line."""
        try:
            generation = response.generations[0][0]
        except (IndexError, TypeError):
            return

        usage_metadata = None
        if hasattr(generation, "message"):
            message = generation.message
            if isinstance(message, AIMessage) and hasattr(message, "usage_metadata"):
                usage_metadata = message.usage_metadata

        identity = _extract_fingerprint(response)
        tokens_in = (usage_metadata or {}).get("input_tokens", 0)
        tokens_out = (usage_metadata or {}).get("output_tokens", 0)

        end_monotonic = time.monotonic()

        with self._lock:
            self.tokens_in += tokens_in
            self.tokens_out += tokens_out
            self.fingerprints.append(identity)
            self._call_seq += 1
            seq = self._call_seq

            start_t = self._start_times.pop(str(run_id), None) if run_id else None
            latency_ms = (
                int((end_monotonic - start_t) * 1000) if start_t is not None else None
            )

            if self.jsonl_path is not None:
                record = {
                    "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "type": "llm_end",
                    "session_id": self.session_id,
                    "call_seq": seq,
                    "call_id": str(run_id) if run_id is not None else None,
                    "model": identity["model"],
                    "fingerprint": identity["fingerprint"],
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "latency_ms": latency_ms,
                    "tags": list(tags) if tags else [],
                    # ``metadata`` from LangGraph typically carries
                    # ``langgraph_node`` and ``langgraph_step``, which let
                    # the audit trail attribute a call to a specific graph
                    # node without us having to thread it through the
                    # constructor manually.
                    "metadata": dict(metadata) if isinstance(metadata, dict) else {},
                }
                try:
                    with open(self.jsonl_path, "a", encoding="utf-8") as f:
                        f.write(
                            json.dumps(record, ensure_ascii=False, default=str) + "\n"
                        )
                except Exception as e:
                    # An audit write failure must never break the user's
                    # run — log and move on. T1.3's hash-chained ledger
                    # will tighten this with explicit failure handling.
                    logger.warning("audit jsonl write failed: %s", e)

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        """Increment tool call counter when a tool starts."""
        with self._lock:
            self.tool_calls += 1

    # ------------------------------------------------------------------ #
    # Public read API
    # ------------------------------------------------------------------ #

    def get_stats(self) -> Dict[str, Any]:
        """Return current statistics."""
        with self._lock:
            return {
                "llm_calls": self.llm_calls,
                "tool_calls": self.tool_calls,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
                "fingerprints": list(self.fingerprints),
                "session_id": self.session_id,
                "jsonl_path": str(self.jsonl_path) if self.jsonl_path else None,
            }
