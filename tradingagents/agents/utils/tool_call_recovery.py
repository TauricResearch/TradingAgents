"""
Tool call recovery and logging utilities.

When small/local LLMs fail to produce structured tool_calls and instead
write raw JSON tool invocations in their text content, this module:

1. Detects the hallucinated tool call JSON in the content
2. Re-materializes the parsed calls onto the AIMessage's ``tool_calls`` field

It does NOT execute any tool itself. Execution still happens downstream in the
LangGraph ``ToolNode`` once the rewritten AIMessage (now carrying real
``tool_calls``) flows through the graph. The second element of the returned
tuple is a ``list[ToolMessage]`` that is currently ALWAYS empty — it exists
only so callers can keep the ``[result] + tool_results`` shape if a future
revision starts executing tools here.

All failures (parse errors, unknown tool names) are logged with full context.

Usage in an analyst node:
    result = chain.invoke(state["messages"])
    result, tool_results = recover_tool_calls(result, available_tools, logger)
    # tool_results is always [] today; the ToolNode runs the recovered calls.
    # return {"messages": [result] + tool_results, ...}
"""

import json
import logging
import re
import uuid
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

logger = logging.getLogger(__name__)

# A model that has fallen back to text usually emits its raw call inside an
# explicit <tool_call>…</tool_call> wrapper (Qwen/Hermes/etc.). Anchoring to the
# wrapper is what keeps us from misreading prose that merely *discusses* a tool.
_TOOL_CALL_WRAPPER = re.compile(r"<tool_call>\s*(\{.*?)\s*</tool_call>", re.DOTALL)

# A finalized report is markdown prose, not a tool call. If the content reads
# like a report (markdown headings / substantial length without a wrapper), we
# do NOT scan it for bare JSON — that's where the old non-nested regex
# false-positived on report text.
_REPORT_MARKERS = re.compile(r"^\s{0,3}#{1,6}\s|\n\s{0,3}#{1,6}\s")
# Recognised call shapes once we have an isolated JSON object.
_NAME_KEYS = ("name", "function")
_ARGS_KEYS = ("arguments", "args", "kwargs", "parameters")


def _build_tool_map(tools: list) -> dict[str, Any]:
    """Return {tool_name: tool} mapping from a list of langchain tools."""
    return {t.name: t for t in tools}


def _iter_json_objects(text: str):
    """Yield each top-level ``{...}`` substring in *text* using a brace-aware
    scanner that respects string literals and escapes.

    Unlike a ``[^{}]*`` regex this correctly captures objects with *nested*
    braces (e.g. ``"arguments": {"filters": {...}}``), so nested-arg calls are
    no longer truncated mid-object.
    """
    depth = 0
    start = -1
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start != -1:
                yield text[start : i + 1]
                start = -1


def _extract_call(obj: dict) -> tuple[str, dict] | None:
    """Map a parsed JSON object onto (tool_name, args) if it looks like a call."""
    name = next((obj[k] for k in _NAME_KEYS if isinstance(obj.get(k), str)), None)
    if not name:
        return None
    args = next((obj[k] for k in _ARGS_KEYS if isinstance(obj.get(k), dict)), None)
    if args is None:
        args = {}
    return name, args


def _candidate_call_objects(content: str):
    """Yield parsed JSON objects that may be hallucinated tool calls.

    Detection is anchored to an explicit ``<tool_call>`` wrapper first. Only
    when no wrapper is present *and* the content does not read like a finalized
    markdown report do we scan bare JSON objects — this avoids re-triggering a
    tool round on report prose that merely mentions a tool call.
    """
    wrappers = _TOOL_CALL_WRAPPER.findall(content)
    if wrappers:
        for raw in wrappers:
            for blob in _iter_json_objects(raw):
                try:
                    obj = json.loads(blob)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield obj, blob
        return

    # No wrapper: refuse to scan prose reports for bare JSON.
    if _REPORT_MARKERS.search(content):
        return
    for blob in _iter_json_objects(content):
        try:
            obj = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and any(k in obj for k in _NAME_KEYS):
            yield obj, blob


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
    parse each detected call and re-materialize it onto a new AIMessage's
    ``tool_calls`` field. This function does NOT execute the tools — the
    downstream LangGraph ``ToolNode`` runs them once the rewritten message flows
    through the graph.

    All failures (parse errors, unknown tool names) are logged at WARNING level
    with full detail.

    Returns:
        (result, tool_messages) — ``tool_messages`` is ALWAYS ``[]`` (no tool is
        executed here); ``result`` is the rewritten AIMessage when calls were
        recovered, otherwise the original.
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
    seen_signatures = set()
    attempts = 0

    for obj, blob in _candidate_call_objects(content):
        extracted = _extract_call(obj)
        if extracted is None:
            continue
        name, args = extracted
        attempts += 1

        log.warning(
            "[ToolCallRecovery] LLM hallucinated raw tool call text — attempting recovery. "
            "Tool: %r  Raw args snippet: %.200s",
            name,
            blob,
        )

        if name not in tool_map:
            log.warning(
                "[ToolCallRecovery] Unknown tool name %r — skipping.",
                name,
            )
            continue

        # Deduplicate on the (name, args) pair, not the raw text, so equivalent
        # calls formatted differently collapse to one.
        call_signature = f"{name}:{json.dumps(args, sort_keys=True)}"
        if call_signature in seen_signatures:
            continue
        seen_signatures.add(call_signature)

        call_id = str(uuid.uuid4())[:8]
        recovered_calls.append({
            "name": name,
            "args": args,
            "id": call_id,
        })
        log.info("[ToolCallRecovery] Successfully parsed recovered tool call %r (id=%s).", name, call_id)

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
