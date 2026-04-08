"""Utility for running an LLM tool-calling loop within a single graph node.

The existing trading-graph agents rely on separate ToolNode graph nodes for
tool execution.  Scanner agents are simpler — they run in a single node per
phase — so they need an inline tool-execution loop.
"""

from __future__ import annotations

import time
from typing import Any, List

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tradingagents.agents.utils.llm_guard import invoke_with_timeout
from tradingagents.default_config import DEFAULT_CONFIG


# Most LLM tool-calling patterns resolve within 2-3 rounds;
# 5 provides headroom for complex scenarios while preventing runaway loops.
MAX_TOOL_ROUNDS = 5

# If the LLM's first response has no tool calls AND is shorter than this,
# a nudge message is appended to encourage tool usage.
# Set high enough to catch models that dump planning text (~500-1000 chars)
# without actually calling tools.
MIN_REPORT_LENGTH = 2000

# Bound tool outputs fed back into the model to avoid oversized second-turn
# prompts that can stall local tool-calling models.
MAX_TOOL_OUTPUT_CHARS = 1800


def run_tool_loop(
    chain,
    messages: List[Any],
    tools: List[Any],
    max_rounds: int = MAX_TOOL_ROUNDS,
    min_report_length: int = MIN_REPORT_LENGTH,
    max_tool_output_chars: int = MAX_TOOL_OUTPUT_CHARS,
    invoke_timeout_seconds: float | None = None,
) -> AIMessage:
    """Invoke *chain* in a loop, executing any tool calls until the LLM
    produces a final text response (i.e. no more tool_calls).

    If the very first LLM response contains no tool calls **and** the text
    is shorter than *min_report_length*, the loop appends a nudge message
    asking the LLM to call tools first, then re-invokes once before
    accepting the response.  This prevents under-powered models from
    skipping tool use when overwhelmed by long context.

    Args:
        chain: A LangChain runnable (prompt | llm.bind_tools(tools)).
        messages: The initial list of messages to send.
        tools: List of LangChain tool objects (must match the tools bound to the LLM).
        max_rounds: Maximum number of tool-calling rounds before forcing a stop.
        min_report_length: Minimum acceptable length (chars) of a text-only
            first response.  Shorter responses trigger a nudge to use tools.

    Returns:
        The final AIMessage with a text ``content`` (report).
    """
    tool_map = {t.name: t for t in tools}
    current_messages = list(messages)
    first_round = True
    result = None
    timeout_seconds = float(
        invoke_timeout_seconds
        or DEFAULT_CONFIG.get("mid_think_llm_timeout")
        or DEFAULT_CONFIG.get("llm_timeout")
        or 120.0
    )
    timeout_seconds = min(
        timeout_seconds,
        float(DEFAULT_CONFIG.get("tool_loop_timeout_cap") or 60.0),
    )

    for _ in range(max_rounds):
        try:
            result, invoke_error = invoke_with_timeout(
                llm=chain,
                prompt_or_messages=current_messages,
                timeout_seconds=timeout_seconds,
            )
            if invoke_error is not None:
                if isinstance(invoke_error, TimeoutError):
                    tool_names = ", ".join(tool_map.keys()) or "preloaded tools"
                    return AIMessage(
                        content=(
                            f"- Tool-using analyst timed out after {timeout_seconds:.0f}s.\n"
                            f"- Available tools for this node: {tool_names}.\n"
                            "- Treat this node as incomplete and do not infer additional unsourced claims."
                        )
                    )
                raise invoke_error
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                raise RuntimeError(
                    f"LLM returned 404 — model may be blocked by provider policy.\n"
                    f"Original: {exc}\n"
                    f"If using OpenRouter: https://openrouter.ai/settings/privacy\n"
                    f"Or set TRADINGAGENTS_QUICK/MID/DEEP_THINK_FALLBACK_LLM."
                ) from exc
            raise
        current_messages.append(result)

        if not result.tool_calls:
            # Nudge: if the LLM skipped tools on its first turn and the
            # response is suspiciously short, ask it to try again with tools.
            if first_round and len(result.content or "") < min_report_length:
                tool_names = ", ".join(tool_map.keys())
                nudge = (
                    "Your response was too brief. You MUST call at least one tool "
                    f"({tool_names}) before writing your final report. "
                    "Please call the tools now."
                )
                current_messages.append(
                    HumanMessage(content=nudge)
                )
                first_round = False
                continue
            return result

        first_round = False

        # Execute each requested tool call and append ToolMessages
        from tradingagents.observability import get_run_logger

        rl = get_run_logger()
        for tc in result.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool_fn = tool_map.get(tool_name)
            if tool_fn is None:
                tool_output = f"Error: unknown tool '{tool_name}'"
                if rl:
                    rl.log_tool_call(tool_name, str(tool_args)[:120], False, 0, error="unknown tool")
            else:
                t0 = time.time()
                try:
                    tool_output = tool_fn.invoke(tool_args)
                    if rl:
                        rl.log_tool_call(tool_name, str(tool_args)[:120], True, (time.time() - t0) * 1000)
                except Exception as e:
                    tool_output = f"Error calling {tool_name}: {e}"
                    if rl:
                        rl.log_tool_call(tool_name, str(tool_args)[:120], False, (time.time() - t0) * 1000, error=str(e)[:200])

            raw_tool_output = str(tool_output)
            tool_output_text = raw_tool_output
            if max_tool_output_chars > 0 and len(tool_output_text) > max_tool_output_chars:
                head = max(200, max_tool_output_chars - 220)
                tool_output_text = (
                    f"{tool_output_text[:head]}\n"
                    f"... [truncated {len(raw_tool_output) - head} chars for tool-loop context safety]"
                )

            current_messages.append(
                ToolMessage(content=tool_output_text, tool_call_id=tc["id"])
            )

    # If we exhausted max_rounds, return the last AIMessage
    # (it may have tool_calls but we treat the content as the report)
    if result is None:
        raise RuntimeError("Tool loop did not produce any LLM response")
    return result
