"""LangChain callback handler that bridges per-step LLM/tool activity
into the dashboard's event protocol.

Attach a single instance per run via ``TradingAgentsGraph(callbacks=[...])``
(or by wrapping the LLM directly via the ``callbacks`` kwarg on
``NormalizedChatOpenAI`` / ``NormalizedChatAnthropic`` / etc.).

The handler takes an explicit ``broadcast`` callable so the unit tests
can capture events without going through the WS plumbing.
"""
from __future__ import annotations

from typing import Any, Callable, Optional
from langchain_core.callbacks import BaseCallbackHandler


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
                        self._emit("analyst_thinking", {"text_fragment": content[:500]})
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
