"""Utility for running an LLM tool-calling loop within a single graph node.

The existing trading-graph agents rely on separate ToolNode graph nodes for
tool execution.  Scanner agents are simpler — they run in a single node per
phase — so they need an inline tool-execution loop.
"""

from __future__ import annotations

import logging
import time
from typing import Any, List

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tradingagents.agents.utils.llm_guard import invoke_with_timeout
from tradingagents.default_config import DEFAULT_CONFIG


# Most LLM tool-calling patterns resolve within 2-3 rounds;
# 5 provides headroom for complex scenarios while preventing runaway loops.
MAX_TOOL_ROUNDS = 5

# If the LLM produces no tool calls AND the response is shorter than this,
# a nudge message is appended to encourage tool usage.
# Set high enough to catch models that dump planning text (~500-1000 chars)
# without actually calling tools.
MIN_REPORT_LENGTH = 2000

# Maximum number of nudges to send when the model keeps producing short
# text-only responses instead of calling tools.  More than 1 nudge is
# needed for weaker models (e.g. minimax) that acknowledge the nudge but
# still don't emit tool_calls on the first retry.
MAX_NUDGES = 2

# Bound tool outputs fed back into the model to avoid oversized second-turn
# prompts that can stall local tool-calling models.
MAX_TOOL_OUTPUT_CHARS = 1800

logger = logging.getLogger(__name__)


def run_tool_loop(
    chain,
    messages: List[Any],
    tools: List[Any],
    max_rounds: int = MAX_TOOL_ROUNDS,
    min_report_length: int = MIN_REPORT_LENGTH,
    max_tool_output_chars: int = MAX_TOOL_OUTPUT_CHARS,
    invoke_timeout_seconds: float | None = None,
    require_tool_result: bool = False,
    node_name: str = "",
) -> AIMessage:
    """Invoke *chain* in a loop, executing any tool calls until the LLM
    produces a final text response (i.e. no more tool_calls).

    If the LLM response contains no tool calls **and** the text is shorter
    than *min_report_length* **and** no tools have been used yet in this
    loop, the loop appends a nudge message asking the LLM to call tools
    first and re-invokes — up to ``MAX_NUDGES`` (2) times.  Once any tool
    has been used, nudging stops so the final synthesis pass is never
    interrupted.  This prevents under-powered models from skipping tool
    use when overwhelmed by long context.

    Args:
        chain: A LangChain runnable (prompt | llm.bind_tools(tools)).
        messages: The initial list of messages to send.
        tools: List of LangChain tool objects (must match the tools bound to the LLM).
        max_rounds: Maximum number of tool-calling rounds before forcing a stop.
        min_report_length: Minimum acceptable length (chars) of a text-only
            first response.  Shorter responses trigger a nudge to use tools.
        require_tool_result: When True and no tool was ever successfully called,
            return a structured ``[INSUFFICIENT_EVIDENCE]`` message instead of
            whatever text the model produced.
        node_name: Human-readable node identifier included in timeout and
            insufficient-evidence messages for downstream diagnostics.

    Returns:
        The final AIMessage with a text ``content`` (report).
    """
    tool_map = {t.name: t for t in tools}
    current_messages = list(messages)
    nudge_count = 0
    tools_ever_used = False
    attempted_tools: list[str] = []
    successful_tools: list[str] = []
    result = None
    _cap = float(DEFAULT_CONFIG.get("tool_loop_timeout_cap") or DEFAULT_CONFIG.get("quick_think_llm_timeout_cap") or 300.0)
    timeout_seconds = min(
        float(invoke_timeout_seconds or DEFAULT_CONFIG.get("quick_think_llm_timeout") or DEFAULT_CONFIG.get("llm_timeout") or _cap),
        _cap,
    )

    def _insufficient_evidence(reason: str) -> AIMessage:
        required_tools = ", ".join(tool_map.keys()) or "none"
        attempted = ", ".join(attempted_tools) or "none"
        missing_tools = [
            tool_name for tool_name in tool_map
            if tool_name not in set(successful_tools)
        ]
        missing = ", ".join(missing_tools) or "none"
        label = node_name or "unknown"
        warning = (
            f"Insufficient evidence in {label}: {reason}; "
            f"missing successful tool results for {missing}; attempted={attempted}"
        )
        logger.warning(warning)
        try:
            from tradingagents.observability import get_run_logger

            rl = get_run_logger()
            if rl:
                rl.log_warning(warning)
        except Exception:
            # Observability should never turn a controlled fallback into a node failure.
            pass

        return AIMessage(
            content=(
                "[INSUFFICIENT_EVIDENCE]\n"
                f"Node: {label}\n"
                f"Reason: {reason}\n"
                f"Missing evidence: no successful tool results from required tools: {missing}.\n"
                f"Required tools: {required_tools}\n"
                f"Attempted tools: {attempted}\n"
                "Downstream handling: treat this node as incomplete; exclude its claims "
                "and do not infer additional unsourced candidates."
            )
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
                    return _insufficient_evidence(
                        f"node timed out after {timeout_seconds:.0f}s before producing usable tool-grounded analysis"
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
            # Nudge: if the LLM has not yet used any tools and the response is
            # suspiciously short, ask it to call tools.  Allow up to MAX_NUDGES
            # retries so that weaker models (e.g. minimax) that acknowledge the
            # nudge in text but don't immediately emit tool_calls still get a
            # second chance.  Never nudge after tools have already been used —
            # at that point the LLM is writing its final synthesis.
            if (
                not tools_ever_used
                and nudge_count < MAX_NUDGES
                and len(result.content or "") < min_report_length
            ):
                tool_names = ", ".join(tool_map.keys())
                nudge = (
                    "Your response was too brief. You MUST call at least one tool "
                    f"({tool_names}) before writing your final report. "
                    "Please call the tools now."
                )
                current_messages.append(
                    HumanMessage(content=nudge)
                )
                nudge_count += 1
                continue
            if require_tool_result and not tools_ever_used:
                return _insufficient_evidence(
                    "model produced final prose without any successful required tool result"
                )
            return result

        # Execute each requested tool call and append ToolMessages
        from tradingagents.observability import get_run_logger

        rl = get_run_logger()
        any_tool_succeeded = False
        for tc in result.tool_calls:
            tool_name = tc["name"]
            attempted_tools.append(tool_name)
            tool_args = tc["args"]
            tool_fn = tool_map.get(tool_name)
            if tool_fn is None:
                valid_names = ", ".join(tool_map.keys())
                tool_output = (
                    f"Error: unknown tool '{tool_name}'. "
                    f"Valid tools are: {valid_names}. "
                    "Please call one of the valid tools instead."
                )
                if rl:
                    rl.log_warning(
                        f"LLM called unknown tool '{tool_name}' — hallucinated name; "
                        f"valid tools: {valid_names}"
                    )
                    rl.log_tool_call(tool_name, str(tool_args)[:120], False, 0, error="unknown tool")
            else:
                t0 = time.time()
                try:
                    tool_output = tool_fn.invoke(tool_args)
                    any_tool_succeeded = True
                    successful_tools.append(tool_name)
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

        # Only count this round as "tools used" if at least one call succeeded.
        # Hallucinated tool names return error ToolMessages but should not
        # suppress the nudge — the LLM still needs to call a real tool.
        if any_tool_succeeded:
            tools_ever_used = True

    # If we exhausted max_rounds, return the last AIMessage
    # (it may have tool_calls but we treat the content as the report)
    if result is None:
        raise RuntimeError("Tool loop did not produce any LLM response")

    # When tools are required but none succeeded, return a structured
    # insufficient-evidence message so downstream nodes can detect failure.
    if require_tool_result and not tools_ever_used:
        return _insufficient_evidence(
            f"no successful tool results obtained after {max_rounds} rounds"
        )

    return result
