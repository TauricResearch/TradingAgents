"""Shared utilities for analyst tool-calling loops.

The key export is :func:`dispatch_tool_calls`, which runs all tool calls
returned in a single LLM step concurrently.  Since each tool call is an
independent HTTP/IO request this roughly halves analyst latency when the
LLM batches multiple calls in a single step (e.g. the fundamentals analyst
calling get_fundamentals, get_balance_sheet, get_cashflow, and
get_income_statement at once).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from langchain_core.messages import ToolMessage


def dispatch_tool_calls(
    tool_map: Dict[str, Any],
    tool_calls: List[dict],
) -> List[ToolMessage]:
    """Execute *tool_calls* concurrently and return ``ToolMessage`` objects.

    For a single tool call the overhead of a thread pool is avoided; the
    call is dispatched inline.  For multiple calls a ``ThreadPoolExecutor``
    is used so that independent HTTP requests overlap.

    The returned list preserves the original *tool_calls* ordering so the
    messages list remains deterministic regardless of which future completes
    first.

    Args:
        tool_map: ``{tool_name: tool}`` mapping built from ``llm.bind_tools(tools)``.
        tool_calls:  The ``result.tool_calls`` list from an LLM response.

    Returns:
        A list of ``ToolMessage`` objects ready to append to the messages list.
    """
    if not tool_calls:
        return []

    if len(tool_calls) == 1:
        tc = tool_calls[0]
        output = tool_map[tc["name"]].invoke(tc["args"])
        return [ToolMessage(content=str(output), tool_call_id=tc["id"], name=tc["name"])]

    # Multiple calls — dispatch concurrently (IO-bound, safe to thread).
    with ThreadPoolExecutor(max_workers=min(len(tool_calls), 8)) as executor:
        futures = {
            executor.submit(tool_map[tc["name"]].invoke, tc["args"]): tc
            for tc in tool_calls
        }
        results: Dict[str, Any] = {}
        for future, tc in futures.items():
            results[tc["id"]] = future.result()

    # Return in the original submission order for a deterministic message list.
    return [
        ToolMessage(
            content=str(results[tc["id"]]),
            tool_call_id=tc["id"],
            name=tc["name"],
        )
        for tc in tool_calls
    ]
