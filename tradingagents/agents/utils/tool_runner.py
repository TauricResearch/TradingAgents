from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Tuple

from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.runnables import Runnable


def run_chain_with_tools(
    chain: Runnable,
    tools: Iterable[Any],
    initial_messages: Iterable[BaseMessage],
    *,
    max_iterations: int = 6,
    logger: Any = None,
) -> Tuple[Any, List[BaseMessage], int]:
    """Execute a LangChain Runnable, fulfilling any tool calls until text is produced."""

    messages: List[BaseMessage] = list(initial_messages)
    tool_map: Dict[str, Any] = {
        getattr(tool, "name", ""): tool for tool in tools if getattr(tool, "name", None)
    }
    last_result: Any = None
    tool_runs = 0

    for _ in range(max_iterations):
        last_result = chain.invoke(messages)
        messages.append(last_result)
        tool_calls = getattr(last_result, "tool_calls", None) or []
        if not tool_calls:
            return last_result, messages, tool_runs

        for call in tool_calls:
            tool_runs += 1
            tool_name = call.get("name") or call.get("tool_name") or ""
            raw_args = call.get("args") or call.get("arguments") or {}
            if isinstance(raw_args, str):
                try:
                    tool_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    tool_args = {"raw": raw_args}
            else:
                tool_args = raw_args

            tool = tool_map.get(tool_name)
            if not tool:
                output = {"error": f"Tool '{tool_name}' unavailable."}
            else:
                try:
                    output = tool.invoke(tool_args)
                except Exception as exc:  # pragma: no cover - defensive logging
                    if logger:
                        logger.warning("Tool %s failed: %s", tool_name, exc)
                    output = {"error": str(exc)}

            messages.append(
                ToolMessage(
                    content=_stringify(output),
                    tool_call_id=call.get("id") or call.get("tool_call_id") or tool_name or "tool-call",
                    name=tool_name or None,
                )
            )

    raise RuntimeError("Tool loop exceeded max iterations before producing a response.")


def extract_text_from_content(content: Any) -> str:
    """Normalize structured message content into printable text."""

    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if "text" in item and isinstance(item["text"], str):
                    parts.append(item["text"])
                elif "content" in item and isinstance(item["content"], str):
                    parts.append(item["content"])
            else:
                parts.append(str(item))
        return "\n".join(part.strip() for part in parts if part).strip()
    if isinstance(content, dict):
        return json.dumps(content, default=str)
    return str(content)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except TypeError:  # pragma: no cover - fallback
        return str(value)
