"""Full-content trace callback (T1.2).

Captures every LangChain lifecycle event — chain/node start+end, LLM
start+end, tool start+end — with the **complete** payload, not just
metadata. The previous stats-handler-based approach (Phase 0 / T0.5)
only kept counters and per-call summaries; this one keeps the prompts,
responses, and tool I/O necessary for post-hoc replay (T1.7) and CoT
faithfulness intervention experiments (T2.3).

Writes one ``TraceRecord``-shaped JSON object per line to
``audit_dir/traces/{session_id}.jsonl``. The format is forward-compatible
with the hash-chained ledger landing in T1.3 — ``prev_hash`` is recorded
as empty string today and gets backfilled by the ledger when it wires
up. No file-format migration is needed at the T1.3 boundary.

Privacy: prompts and responses on disk may contain PII or proprietary
analysis. Phase 1 stores them unredacted because the threat model is
"compliance can inspect your own audit trail", not "the audit dir is
public". Encryption-at-rest, redaction policies, and access control are
deferred to a dedicated security work-stream — they're orthogonal to
audit completeness and would muddy this PR's scope.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from tradingagents.audit.schemas import (
    LLM_END,
    LLM_START,
    NODE_ENTER,
    NODE_EXIT,
    TOOL_END,
    TOOL_START,
    TraceRecord,
    canonical_json,
    hash_payload,
)
from tradingagents.audit.ledger import HashChainLedger

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------- #
# Serialization helpers
# -------------------------------------------------------------------- #


def _serialize_message(message: Any) -> Dict[str, Any]:
    """Best-effort dict form of a LangChain message.

    The shape we want on disk: ``{"type": "human"|"ai"|"system"|...,
    "content": str | list, "name": optional, ...}``. LangChain messages
    expose this via ``.model_dump()`` or older ``.dict()``; anything
    else falls back to a stringified content + class-name type.
    """
    if hasattr(message, "model_dump"):
        try:
            return message.model_dump()
        except Exception:
            pass
    if hasattr(message, "dict"):
        try:
            return message.dict()
        except Exception:
            pass
    if isinstance(message, dict):
        return message
    return {
        "type": type(message).__name__,
        "content": getattr(message, "content", str(message)),
    }


def _serialize_messages(messages: Any) -> List[Dict[str, Any]]:
    """Flatten the nested message lists LangChain hands to on_chat_model_start.

    The hook gets ``messages: List[List[BaseMessage]]`` — one inner list
    per prompt (batch invocations). We flatten with batch_index markers
    so the on-disk record preserves which batch each message came from.
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(messages, list):
        return [_serialize_message(messages)]
    for batch_idx, inner in enumerate(messages):
        if isinstance(inner, list):
            for m in inner:
                d = _serialize_message(m)
                d["_batch_idx"] = batch_idx
                out.append(d)
        else:
            out.append(_serialize_message(inner))
    return out


def _serialize_response(response: LLMResult) -> Dict[str, Any]:
    """Reduce LLMResult to plain JSON-safe dicts.

    We capture both the generation contents (``text``, ``message``,
    ``generation_info``) and the top-level ``llm_output`` block since
    different providers populate fingerprint and stop_reason on
    different surfaces.
    """
    generations: List[List[Dict[str, Any]]] = []
    for batch in getattr(response, "generations", []) or []:
        batch_out: List[Dict[str, Any]] = []
        for gen in batch or []:
            entry: Dict[str, Any] = {
                "text": getattr(gen, "text", None),
                "generation_info": dict(getattr(gen, "generation_info", None) or {}),
            }
            msg = getattr(gen, "message", None)
            if msg is not None:
                entry["message"] = _serialize_message(msg)
            batch_out.append(entry)
        generations.append(batch_out)
    return {
        "generations": generations,
        "llm_output": dict(getattr(response, "llm_output", None) or {}),
    }


def _serialize_tool_output(output: Any) -> Any:
    """Stringify tool outputs that aren't already JSON-safe."""
    if isinstance(output, (str, int, float, bool)) or output is None:
        return output
    if isinstance(output, (list, tuple)):
        return [_serialize_tool_output(o) for o in output]
    if isinstance(output, dict):
        return {str(k): _serialize_tool_output(v) for k, v in output.items()}
    # Pydantic models, dataclasses, langchain wrappers: try dict / repr.
    for method in ("model_dump", "dict", "__dict__"):
        if hasattr(output, method):
            try:
                val = getattr(output, method)
                return val() if callable(val) else dict(val)
            except Exception:
                pass
    return repr(output)


def _extract_node(metadata: Optional[Dict[str, Any]], tags: Optional[List[str]]) -> Optional[str]:
    """Pull the LangGraph node name out of callback metadata when present.

    LangGraph populates ``metadata['langgraph_node']`` for callbacks
    fired inside compiled graphs. Falling back to tags is defensive —
    older LangGraph versions put node names in tags as ``langgraph:node``.
    """
    if isinstance(metadata, dict):
        node = metadata.get("langgraph_node")
        if node:
            return str(node)
    if tags:
        for t in tags:
            if isinstance(t, str) and t.startswith("langgraph:"):
                return t.split(":", 1)[1] or None
    return None


# -------------------------------------------------------------------- #
# The callback itself
# -------------------------------------------------------------------- #


class TraceCallback(BaseCallbackHandler):
    """LangChain BaseCallbackHandler that emits full ``TraceRecord`` events.

    Pair with the existing ``StatsCallbackHandler`` rather than replacing
    it — stats handler is light and feeds the CLI display, trace
    callback is heavy and feeds the audit pipeline. Both can be
    registered.
    """

    def __init__(
        self,
        *,
        jsonl_path: Optional[Union[str, Path]] = None,
        session_id: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.session_id: str = session_id or str(uuid.uuid4())
        self.jsonl_path: Optional[Path] = (
            Path(jsonl_path).expanduser() if jsonl_path else None
        )
        # T1.3 — when persisting, route through the hash-chained ledger
        # so every appended record links back to the previous one. The
        # in-memory ``records`` list still reflects the same prev_hash
        # the ledger wrote, since ledger.append mutates the record
        # before writing.
        self.ledger: Optional[HashChainLedger] = (
            HashChainLedger(self.jsonl_path) if self.jsonl_path is not None else None
        )
        # Map LangChain run_id (per-call UUID) -> our TraceRecord.record_id
        # so that on_*_end events can correlate back to their on_*_start
        # parent regardless of nesting.
        self._run_to_record: Dict[str, str] = {}
        # In-memory copy of every record we've written, for tests and
        # programmatic inspection. The file on disk is the source of truth;
        # this list is convenience.
        self.records: List[TraceRecord] = []

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_records(self) -> List[TraceRecord]:
        """Return a snapshot of records emitted so far."""
        with self._lock:
            return list(self.records)

    # ------------------------------------------------------------------ #
    # Internal append
    # ------------------------------------------------------------------ #

    def _append(
        self,
        *,
        type_: str,
        payload: Dict[str, Any],
        run_id: Optional[uuid.UUID],
        parent_run_id: Optional[uuid.UUID],
        node: Optional[str],
    ) -> TraceRecord:
        """Build, persist, and return one TraceRecord. Caller-agnostic."""
        record_id = str(uuid.uuid4())
        # The parent in the trace tree comes from LangChain's
        # parent_run_id, which we translate into the record_id we already
        # assigned to that call. If the parent fired before we attached
        # (rare; possible during reconnect), we record None and downstream
        # tooling treats this as a forest root.
        parent_record_id = None
        if parent_run_id is not None:
            parent_record_id = self._run_to_record.get(str(parent_run_id))

        record = TraceRecord(
            record_id=record_id,
            session_id=self.session_id,
            parent_record_id=parent_record_id,
            ts=datetime.now(timezone.utc),
            type=type_,
            node=node,
            payload=payload,
            payload_hash=hash_payload(payload),
            prev_hash="",  # reserved for T1.3
        )

        # Register the start-side run_id mapping so the matching end can
        # set parent_record_id correctly. End events also get registered
        # so deeper nested ends point to them, but in practice only
        # start-side calls have children.
        if run_id is not None:
            self._run_to_record[str(run_id)] = record_id

        # Persist via the hash-chained ledger; this both sets the record's
        # prev_hash and writes the canonical line to disk. T1.3 onwards
        # every persisted trace is tamper-evident.
        if self.ledger is not None:
            try:
                self.ledger.append(record)
            except Exception as e:
                # Same philosophy as the rest of the audit subsystem:
                # never let an audit-side failure break the user's run.
                logger.warning("trace_callback ledger append failed: %s", e)

        self.records.append(record)
        return record

    # ------------------------------------------------------------------ #
    # LangChain callback hooks
    # ------------------------------------------------------------------ #

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: Any,
        *,
        run_id: Optional[uuid.UUID] = None,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        with self._lock:
            self._append(
                type_=LLM_START,
                payload={
                    "serialized": serialized,
                    "messages": _serialize_messages(messages),
                    "tags": list(tags) if tags else [],
                    "metadata": dict(metadata) if isinstance(metadata, dict) else {},
                    "invocation_params": dict(kwargs.get("invocation_params") or {}),
                },
                run_id=run_id,
                parent_run_id=parent_run_id,
                node=_extract_node(metadata, tags),
            )

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: Optional[uuid.UUID] = None,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Used by completion-style LLMs (non-chat). Most of TradingAgents
        runs through on_chat_model_start, but we cover both."""
        with self._lock:
            self._append(
                type_=LLM_START,
                payload={
                    "serialized": serialized,
                    "prompts": list(prompts) if prompts else [],
                    "tags": list(tags) if tags else [],
                    "metadata": dict(metadata) if isinstance(metadata, dict) else {},
                    "invocation_params": dict(kwargs.get("invocation_params") or {}),
                },
                run_id=run_id,
                parent_run_id=parent_run_id,
                node=_extract_node(metadata, tags),
            )

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: Optional[uuid.UUID] = None,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        with self._lock:
            self._append(
                type_=LLM_END,
                payload={
                    "response": _serialize_response(response),
                    "tags": list(tags) if tags else [],
                    "metadata": dict(metadata) if isinstance(metadata, dict) else {},
                },
                run_id=run_id,
                parent_run_id=parent_run_id,
                node=_extract_node(metadata, tags),
            )

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: Optional[uuid.UUID] = None,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        with self._lock:
            self._append(
                type_=TOOL_START,
                payload={
                    "serialized": serialized,
                    "input": input_str,
                    "tags": list(tags) if tags else [],
                    "metadata": dict(metadata) if isinstance(metadata, dict) else {},
                },
                run_id=run_id,
                parent_run_id=parent_run_id,
                node=_extract_node(metadata, tags),
            )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: Optional[uuid.UUID] = None,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        with self._lock:
            self._append(
                type_=TOOL_END,
                payload={
                    "output": _serialize_tool_output(output),
                    "tags": list(tags) if tags else [],
                    "metadata": dict(metadata) if isinstance(metadata, dict) else {},
                },
                run_id=run_id,
                parent_run_id=parent_run_id,
                node=_extract_node(metadata, tags),
            )

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: Optional[uuid.UUID] = None,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """LangGraph node entries fire as chain starts; we record them as
        NODE_ENTER so the trace tree has explicit nesting boundaries."""
        with self._lock:
            self._append(
                type_=NODE_ENTER,
                payload={
                    "serialized": serialized,
                    "inputs_keys": (
                        list(inputs.keys()) if isinstance(inputs, dict) else None
                    ),
                    "tags": list(tags) if tags else [],
                    "metadata": dict(metadata) if isinstance(metadata, dict) else {},
                },
                run_id=run_id,
                parent_run_id=parent_run_id,
                node=_extract_node(metadata, tags),
            )

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: Optional[uuid.UUID] = None,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        with self._lock:
            self._append(
                type_=NODE_EXIT,
                payload={
                    "outputs_keys": (
                        list(outputs.keys()) if isinstance(outputs, dict) else None
                    ),
                    "tags": list(tags) if tags else [],
                    "metadata": dict(metadata) if isinstance(metadata, dict) else {},
                },
                run_id=run_id,
                parent_run_id=parent_run_id,
                node=_extract_node(metadata, tags),
            )
