"""Utility for running an LLM tool-calling loop within a single graph node.

The existing trading-graph agents rely on separate ToolNode graph nodes for
tool execution.  Scanner agents are simpler — they run in a single node per
phase — so they need an inline tool-execution loop.
"""

from __future__ import annotations

from typing import Any, List

from langchain_core.messages import AIMessage, ToolMessage


# Most LLM tool-calling patterns resolve within 2-3 rounds;
# 5 provides headroom for complex scenarios while preventing runaway loops.
MAX_TOOL_ROUNDS = 5


def run_tool_loop(
    chain,
    messages: List[Any],
    tools: List[Any],
    max_rounds: int = MAX_TOOL_ROUNDS,
) -> AIMessage:
    """Invoke *chain* in a loop, executing any tool calls until the LLM
    produces a final text response (i.e. no more tool_calls).

    Args:
        chain: A LangChain runnable (prompt | llm.bind_tools(tools)).
        messages: The initial list of messages to send.
        tools: List of LangChain tool objects (must match the tools bound to the LLM).
        max_rounds: Maximum number of tool-calling rounds before forcing a stop.

    Returns:
        The final AIMessage with a text ``content`` (report).
    """
    tool_map = {t.name: t for t in tools}
    current_messages = list(messages)

    for _ in range(max_rounds):
        result: AIMessage = chain.invoke(current_messages)
        current_messages.append(result)

        if not result.tool_calls:
            return result

        # Execute each requested tool call and append ToolMessages
        for tc in result.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool_fn = tool_map.get(tool_name)
            if tool_fn is None:
                tool_output = f"Error: unknown tool '{tool_name}'"
            else:
                try:
                    tool_output = tool_fn.invoke(tool_args)
                except Exception as e:
                    tool_output = f"Error calling {tool_name}: {e}"

            current_messages.append(
                ToolMessage(content=str(tool_output), tool_call_id=tc["id"])
            )

    # If we exhausted max_rounds, return the last AIMessage
    # (it may have tool_calls but we treat the content as the report)
    return result
