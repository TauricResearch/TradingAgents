"""Structured observability logging for TradingAgents.

Emits JSON-lines logs capturing:
- LLM calls (model, agent/node, token counts, latency)
- Tool calls (tool name, args summary, success/failure, latency)
- Data vendor calls (method, vendor, success/failure, fallback chain)
- Report saves

Usage:
    from tradingagents.observability import RunLogger, get_run_logger

    logger = RunLogger()          # one per run
    # pass logger.callback to LangChain as a callback handler
    # pass logger to route_to_vendor / run_tool_loop via context

All events are written as JSON lines to a file and also to Python's
``logging`` module at DEBUG level for console visibility.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult

_py_logger = logging.getLogger("tradingagents.observability")

# ──────────────────────────────────────────────────────────────────────────────
# Event dataclass — each logged event becomes one JSON line
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class _Event:
    kind: str               # "llm", "tool", "vendor", "report"
    ts: float               # time.time()
    data: dict              # kind-specific payload

    def to_dict(self) -> dict:
        return {"kind": self.kind, "ts": self.ts, **self.data}


# ──────────────────────────────────────────────────────────────────────────────
# RunLogger — accumulates events and writes a JSON-lines log file
# ──────────────────────────────────────────────────────────────────────────────

class RunLogger:
    """Accumulates structured events for a single run (analyze / scan / pipeline).

    Attributes:
        callback: A LangChain ``BaseCallbackHandler`` that can be passed to
            LLM constructors or graph invocations.
        events: Thread-safe list of all recorded events.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.events: list[_Event] = []
        self.callback = _LLMCallbackHandler(self)
        self._start = time.time()

    # -- public helpers to record events from non-callback code ----------------

    def log_vendor_call(
        self,
        method: str,
        vendor: str,
        success: bool,
        duration_ms: float,
        error: str | None = None,
        args_summary: str = "",
    ) -> None:
        """Record a data-vendor call (called from ``route_to_vendor``)."""
        evt = _Event(
            kind="vendor",
            ts=time.time(),
            data={
                "method": method,
                "vendor": vendor,
                "success": success,
                "duration_ms": round(duration_ms, 1),
                "error": error,
                "args": args_summary,
            },
        )
        self._append(evt)

    def log_tool_call(
        self,
        tool_name: str,
        args_summary: str,
        success: bool,
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        """Record a tool invocation (called from ``run_tool_loop``)."""
        evt = _Event(
            kind="tool",
            ts=time.time(),
            data={
                "tool": tool_name,
                "args": args_summary,
                "success": success,
                "duration_ms": round(duration_ms, 1),
                "error": error,
            },
        )
        self._append(evt)

    def log_report_save(self, path: str) -> None:
        """Record that a report file was written."""
        evt = _Event(kind="report", ts=time.time(), data={"path": path})
        self._append(evt)

    # -- summary ---------------------------------------------------------------

    def summary(self) -> dict:
        """Return an aggregated summary suitable for ``run_summary.json``."""
        with self._lock:
            events = list(self.events)

        llm_events = [e for e in events if e.kind == "llm"]
        tool_events = [e for e in events if e.kind == "tool"]
        vendor_events = [e for e in events if e.kind == "vendor"]

        total_tokens_in = sum(e.data.get("tokens_in", 0) for e in llm_events)
        total_tokens_out = sum(e.data.get("tokens_out", 0) for e in llm_events)

        vendor_ok = sum(1 for e in vendor_events if e.data["success"])
        vendor_fail = sum(1 for e in vendor_events if not e.data["success"])

        # Group LLM calls by model
        model_counts: dict[str, int] = {}
        for e in llm_events:
            m = e.data.get("model", "unknown")
            model_counts[m] = model_counts.get(m, 0) + 1

        # Group vendor calls by vendor
        vendor_counts: dict[str, dict] = {}
        for e in vendor_events:
            v = e.data["vendor"]
            if v not in vendor_counts:
                vendor_counts[v] = {"ok": 0, "fail": 0}
            if e.data["success"]:
                vendor_counts[v]["ok"] += 1
            else:
                vendor_counts[v]["fail"] += 1

        # Group vendor calls by vendor → method for detailed breakdown
        vendor_methods: dict[str, dict[str, int]] = {}
        for e in vendor_events:
            v = e.data["vendor"]
            m = e.data.get("method", "unknown")
            if v not in vendor_methods:
                vendor_methods[v] = {}
            vendor_methods[v][m] = vendor_methods[v].get(m, 0) + 1

        return {
            "elapsed_s": round(time.time() - self._start, 1),
            "llm_calls": len(llm_events),
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
            "tokens_total": total_tokens_in + total_tokens_out,
            "models_used": model_counts,
            "tool_calls": len(tool_events),
            "tool_success": sum(1 for e in tool_events if e.data["success"]),
            "tool_fail": sum(1 for e in tool_events if not e.data["success"]),
            "vendor_calls": len(vendor_events),
            "vendor_success": vendor_ok,
            "vendor_fail": vendor_fail,
            "vendors_used": vendor_counts,
            "vendor_methods": vendor_methods,
        }

    def write_log(self, path: Path) -> None:
        """Write all events as JSON lines + a summary block to *path*."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            events = list(self.events)

        lines = [json.dumps(e.to_dict()) for e in events]
        lines.append(json.dumps({"kind": "summary", **self.summary()}))
        path.write_text("\n".join(lines) + "\n")
        _py_logger.info("Run log written to %s", path)

    # -- internals -------------------------------------------------------------

    def _append(self, evt: _Event) -> None:
        with self._lock:
            self.events.append(evt)
        _py_logger.debug("%s | %s", evt.kind, json.dumps(evt.data))


# ──────────────────────────────────────────────────────────────────────────────
# LangChain callback handler — captures LLM call details
# ──────────────────────────────────────────────────────────────────────────────

class _LLMCallbackHandler(BaseCallbackHandler):
    """LangChain callback that feeds LLM events into a ``RunLogger``."""

    def __init__(self, run_logger: RunLogger) -> None:
        super().__init__()
        self._rl = run_logger
        self._lock = threading.Lock()
        # Track in-flight calls: run_id -> metadata
        self._inflight: dict[str, dict] = {}

    # -- chat model start (preferred path for ChatOpenAI / ChatAnthropic) ------

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        model = _extract_model(serialized, kwargs)
        agent = kwargs.get("name") or serialized.get("name") or _extract_graph_node(kwargs)
        key = str(run_id) if run_id else str(id(messages))
        with self._lock:
            self._inflight[key] = {
                "model": model,
                "agent": agent or "",
                "t0": time.time(),
            }

    # -- legacy LLM start (completion-style) -----------------------------------

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        model = _extract_model(serialized, kwargs)
        agent = kwargs.get("name") or serialized.get("name") or _extract_graph_node(kwargs)
        key = str(run_id) if run_id else str(id(prompts))
        with self._lock:
            self._inflight[key] = {
                "model": model,
                "agent": agent or "",
                "t0": time.time(),
            }

    # -- LLM end ---------------------------------------------------------------

    def on_llm_end(self, response: LLMResult, *, run_id: Any = None, **kwargs: Any) -> None:
        key = str(run_id) if run_id else None
        with self._lock:
            meta = self._inflight.pop(key, None) if key else None

        tokens_in = 0
        tokens_out = 0
        model_from_response = ""
        try:
            generation = response.generations[0][0]
            if hasattr(generation, "message"):
                msg = generation.message
                if isinstance(msg, AIMessage) and hasattr(msg, "usage_metadata") and msg.usage_metadata:
                    tokens_in = msg.usage_metadata.get("input_tokens", 0)
                    tokens_out = msg.usage_metadata.get("output_tokens", 0)
                if hasattr(msg, "response_metadata"):
                    model_from_response = msg.response_metadata.get("model_name", "") or msg.response_metadata.get("model", "")
        except (IndexError, TypeError, AttributeError):
            pass

        model = model_from_response or (meta["model"] if meta else "unknown")
        agent = meta["agent"] if meta else ""
        duration_ms = (time.time() - meta["t0"]) * 1000 if meta else 0

        evt = _Event(
            kind="llm",
            ts=time.time(),
            data={
                "model": model,
                "agent": agent,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "duration_ms": round(duration_ms, 1),
            },
        )
        self._rl._append(evt)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _extract_model(serialized: dict, kwargs: dict) -> str:
    """Best-effort model name from LangChain callback metadata."""
    # kwargs.invocation_params often has the model name
    inv = kwargs.get("invocation_params") or {}
    model = inv.get("model_name") or inv.get("model") or ""
    if model:
        return model
    # serialized might have it nested
    kw = serialized.get("kwargs", {})
    return kw.get("model_name") or kw.get("model") or serialized.get("id", [""])[-1]


def _extract_graph_node(kwargs: dict) -> str:
    """Try to get the current graph node name from LangGraph metadata."""
    tags = kwargs.get("tags") or []
    for tag in tags:
        if isinstance(tag, str) and tag.startswith("graph:node:"):
            return tag.split(":", 2)[-1]
    metadata = kwargs.get("metadata") or {}
    return metadata.get("langgraph_node", "")


# ──────────────────────────────────────────────────────────────────────────────
# Thread-local context for passing RunLogger to vendor/tool layers
# ──────────────────────────────────────────────────────────────────────────────

import contextvars as _cv

_current_run_logger: _cv.ContextVar["RunLogger | None"] = _cv.ContextVar(
    "current_run_logger", default=None
)


def set_run_logger(rl: "RunLogger | None") -> None:
    """Set the active RunLogger for the current async task or thread."""
    _current_run_logger.set(rl)


def get_run_logger() -> "RunLogger | None":
    """Get the active RunLogger for the current async task (or None if not set)."""
    return _current_run_logger.get()
