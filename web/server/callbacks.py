"""LangChain callback handler that bridges per-step LLM/tool activity
into the dashboard's event protocol.

Attach a single instance per run via ``TradingAgentsGraph(callbacks=[...])``
(or by wrapping the LLM directly via the ``callbacks`` kwarg on
``NormalizedChatOpenAI`` / ``NormalizedChatAnthropic`` / etc.).

The handler takes an explicit ``broadcast`` callable so the unit tests
can capture events without going through the WS plumbing.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from langchain_core.callbacks import BaseCallbackHandler


_log = logging.getLogger(__name__)


def _broadcast_via_events(run_id: int) -> Callable[[dict], None]:
    """Build a broadcast callable that goes through ``events.emit``.

    Used in production wiring (runner.py) so all emissions land in the
    same DB-write + WS-broadcast path as the runner's manual emits.
    """
    from . import events
    def _b(evt: dict) -> None:
        events.emit(run_id, evt["type"], evt["data"])
    return _b


class StreamingCallbackHandler(BaseCallbackHandler):
    """Maps LangChain's per-step callbacks to WsEvent payloads."""

    def __init__(self, *, run_id: int, broadcast: Optional[Callable[[dict], None]] = None) -> None:
        self.run_id = run_id
        self._broadcast = broadcast or _broadcast_via_events(run_id)

    def _emit(self, type_: str, data: dict) -> None:
        self._broadcast({"v": 1, "type": type_, "ts": "", "run_id": self.run_id, "data": data})

    # ---- LLM -----------------------------------------------------------

    def on_chat_model_start(self, serialized: dict, messages: list, **kw) -> None:
        prompt_preview = _extract_last_user_text(messages)
        self._emit("analyst_thinking", {
            "text_preview": (prompt_preview[:200] if prompt_preview else None),
        })

    def on_llm_end(self, response: Any, **kw) -> None:
        try:
            for gen in response.generations:
                for chat in gen:
                    msg = getattr(chat, "message", None)
                    if msg is None:
                        continue
                    content = str(getattr(msg, "content", "") or "")
                    tool_calls = getattr(msg, "tool_calls", None) or []
                    if content and not tool_calls:
                        self._emit("analyst_thinking", {"text_fragment": content})
                        return
        except Exception:
            return

    # ---- Tools ---------------------------------------------------------

    def on_tool_start(self, serialized: dict, input_str: str, **kw) -> None:
        name = (serialized or {}).get("name", "unknown")
        self._emit("tool_call", {"tool": name, "args": str(input_str)[:200]})

    def on_tool_end(self, output: Any, **kw) -> None:
        text = str(getattr(output, "content", output) or "")
        name = getattr(output, "name", "unknown")
        self._emit("tool_result", {"tool": name, "summary": text[:200]})

    def on_tool_error(self, error: BaseException, **kw) -> None:
        text = str(error)
        self._emit("tool_result", {"tool": "unknown", "error": text, "summary": text[:200]})


def _save_llm_call_default(call_data: dict[str, Any]) -> None:
    """Production default: persist via the llm_calls module."""
    from web.server.llm_calls import save_llm_call
    save_llm_call(**call_data)


class CaptureCallbackHandler(BaseCallbackHandler):
    """Accumulates full LLM prompt->response pairs and persists them.

    Attach alongside StreamingCallbackHandler in the graph's callbacks
    list. Uses ``run_id`` (LangChain's per-call UUID) to correlate
    ``on_chat_model_start`` with ``on_llm_end``.

    The handler does NOT emit dashboard events — it writes directly to
    the ``llm_call`` table via the injected ``save_call`` callable.
    """

    def __init__(
        self,
        *,
        run_id: int,
        ticker: str,
        save_call: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self.run_id = run_id
        self.ticker = ticker
        self._save_call = save_call or _save_llm_call_default
        # LangChain per-call run_id -> pending data
        self._pending: dict[uuid.UUID, dict[str, Any]] = {}
        # Set by the runner's event_callback before each node executes
        self.current_node: Optional[str] = None

    def on_chat_model_start(
        self,
        serialized: dict,
        messages: list,
        *,
        run_id: uuid.UUID,
        **kw: Any,
    ) -> None:
        prompt_parts: list[str] = []
        for batch in messages or []:
            for msg in batch or []:
                role = str(getattr(msg, "type", "unknown"))
                content = str(getattr(msg, "content", "") or "")
                prompt_parts.append(f"{role}: {content}")
        prompt_text = "\n\n".join(prompt_parts)

        self._pending[run_id] = {
            "model": serialized.get("name", "unknown"),
            "prompt_text": prompt_text,
            "started_at": datetime.now(timezone.utc),
        }

    def on_llm_end(self, response: Any, *, run_id: uuid.UUID, **kw: Any) -> None:
        pending = self._pending.pop(run_id, None)
        if pending is None:
            return

        # Extract response text + tool calls
        response_text = ""
        tool_calls: list = []
        try:
            for gen in response.generations:
                for chat in gen:
                    msg = getattr(chat, "message", None)
                    if msg is None:
                        text = str(getattr(chat, "text", "") or "")
                        response_text += text
                        continue
                    content = str(getattr(msg, "content", "") or "")
                    response_text += content
                    tool_calls.extend(getattr(msg, "tool_calls", None) or [])
        except Exception as exc:
            _log.warning("CaptureCallbackHandler: error extracting response: %s", exc)

        # Extract token usage (handle both older and newer LLM result shapes)
        input_tokens = output_tokens = total_tokens = 0
        model = pending["model"]
        try:
            llm_output = getattr(response, "llm_output", None) or {}
            model = llm_output.get("model_name", model)
            usage = llm_output.get("token_usage", None) or {}
            input_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
            output_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
            total_tokens = usage.get("total_tokens", 0)
        except Exception as exc:
            _log.warning("CaptureCallbackHandler: error extracting tokens: %s", exc)

        started_at: datetime = pending["started_at"]
        duration_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)

        self._save_call({
            "run_id": self.run_id,
            "ticker": self.ticker,
            "node_name": self.current_node or "",
            "started_at": started_at,
            "model": model,
            "prompt_text": pending["prompt_text"],
            "response_text": response_text,
            "tool_calls": tool_calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "duration_ms": duration_ms,
        })

    def on_llm_error(self, error: BaseException, *, run_id: uuid.UUID, **kw: Any) -> None:
        """Clean up pending state on LLM error to prevent memory leaks."""
        self._pending.pop(run_id, None)


def _extract_last_user_text(messages: list) -> Optional[str]:
    """Best-effort extraction of the most recent user message text.

    LangChain's on_chat_model_start passes a nested list of message
    lists (one per LLM call inside the agent). The last HumanMessage
    in the last list is the freshest user-authored text.
    """
    try:
        for batch in reversed(messages or []):
            for msg in reversed(batch or []):
                if getattr(msg, "type", None) == "human":
                    return str(msg.content)
    except Exception:
        return None
    return None
