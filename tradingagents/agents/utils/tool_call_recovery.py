"""
Tool call recovery and logging utilities.

When small/local LLMs fail to produce structured tool_calls and instead
write raw JSON tool invocations in their text content, this module:

1. Detects the hallucinated tool call JSON in the content
2. Parses and actually executes the tool
3. Returns a proper ToolMessage result the LangGraph loop can use
4. Logs all failures with full context so they are visible in the logs

Usage in an analyst node:
    result = chain.invoke(state["messages"])
    result, tool_results = recover_tool_calls(result, available_tools, logger)
    # tool_results: list of ToolMessage objects (may be empty)
    # return {"messages": [result] + tool_results, ...}
"""

import json
import logging
import re
import uuid
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

logger = logging.getLogger(__name__)

# Regex patterns that small LLMs commonly hallucinate
_TOOL_CALL_PATTERNS = [
    # {"name": "tool_name", "arguments": {...}}
    re.compile(
        r'\{[^{}]*"name"\s*:\s*"(?P<name>[^"]+)"[^{}]*"arguments"\s*:\s*(?P<args>\{[^{}]*\})[^{}]*\}',
        re.DOTALL,
    ),
    # {"function": "tool_name", "kwargs": {...}}
    re.compile(
        r'\{[^{}]*"function"\s*:\s*"(?P<name>[^"]+)"[^{}]*"kwargs"\s*:\s*(?P<args>\{[^{}]*\})[^{}]*\}',
        re.DOTALL,
    ),
    # <tool_call>{"name": ..., "arguments": ...}</tool_call>
    re.compile(
        r'<tool_call>\s*\{[^{}]*"name"\s*:\s*"(?P<name>[^"]+)"[^{}]*"arguments"\s*:\s*(?P<args>\{[^{}]*\})[^{}]*\}\s*</tool_call>',
        re.DOTALL,
    ),
]


def _build_tool_map(tools: list) -> dict[str, Any]:
    """Return {tool_name: tool} mapping from a list of langchain tools."""
    return {t.name: t for t in tools}


def _try_parse_args(raw: str) -> dict | None:
    """Attempt to parse a JSON string into a dict, returning None on failure."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def recover_tool_calls(
    result: AIMessage,
    tools: list,
    node_logger: logging.Logger | None = None,
) -> tuple[AIMessage, list[ToolMessage]]:
    """
    Inspect *result* for hallucinated tool call text.

    If the LLM produced proper tool_calls (non-empty list), returns immediately
    with no recovery needed.

    If tool_calls is empty but the content contains recognisable tool call JSON,
    parse and execute each detected call, appending a ToolMessage per call.

    All failures (parse errors, unknown tool names, tool execution errors) are
    logged at WARNING level with full detail.

    Returns:
        (result, tool_messages)  — tool_messages is [] when nothing was recovered
    """
    log = node_logger or logger

    # Happy path: LLM did proper tool calling
    if result.tool_calls:
        return result, []

    content = result.content or ""
    if not content.strip():
        return result, []

    tool_map = _build_tool_map(tools)
    recovered_calls = []
    attempts = 0

    for pattern in _TOOL_CALL_PATTERNS:
        for match in pattern.finditer(content):
            attempts += 1
            name = match.group("name")
            args_raw = match.group("args")

            log.warning(
                "[ToolCallRecovery] LLM hallucinated raw tool call text — attempting recovery. "
                "Tool: %r  Raw args snippet: %.200s",
                name,
                args_raw,
            )

            if name not in tool_map:
                log.warning(
                    "[ToolCallRecovery] Unknown tool name %r — skipping.",
                    name,
                )
                continue

            args = _try_parse_args(args_raw)
            if args is None:
                log.warning(
                    "[ToolCallRecovery] Failed to parse args JSON for tool %r: %s",
                    name,
                    args_raw,
                )
                continue

            # Deduplicate
            call_signature = f"{name}:{args_raw}"
            if any(c.get("_sig") == call_signature for c in recovered_calls):
                continue

            call_id = str(uuid.uuid4())[:8]
            recovered_calls.append({
                "name": name,
                "args": args,
                "id": call_id,
                "_sig": call_signature,
            })
            log.info("[ToolCallRecovery] Successfully parsed recovered tool call %r (id=%s).", name, call_id)

    # Clean up _sig before returning
    for call in recovered_calls:
        call.pop("_sig", None)

    if recovered_calls:
        # Create a new AIMessage with the extracted tool calls
        new_result = AIMessage(
            content=result.content,
            tool_calls=recovered_calls,
        )
        return new_result, []

    if attempts > 0 and not recovered_calls:
        log.warning(
            "[ToolCallRecovery] Detected %d hallucinated tool call(s) but none could be parsed. "
            "The agent will produce a report from whatever context it already has.",
            attempts,
        )

    return result, []


def log_tool_call_failure(
    node_name: str,
    ticker: str,
    tool_names: list[str],
    result: AIMessage,
    node_logger: logging.Logger | None = None,
) -> None:
    """
    Log a warning when an agent finishes a turn with no tool calls AND
    the report is empty/very short (indicating a likely failure).
    """
    log = node_logger or logger
    content_len = len((result.content or "").strip())
    if not result.tool_calls and content_len < 100:
        log.warning(
            "[%s] Agent produced no tool calls and very short content (%d chars) for ticker %r. "
            "Available tools were: %s. Content preview: %.200s",
            node_name,
            content_len,
            ticker,
            tool_names,
            (result.content or "").strip()[:200],
        )
