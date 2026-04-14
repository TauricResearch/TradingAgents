"""SDK-native analyst runner.

When the configured LLM is :class:`ChatClaudeAgent`, the analyst node delegates
the whole tool-calling loop to ``claude-agent-sdk``. The SDK owns the loop:
Claude iteratively invokes the translated MCP tools and returns a final text
report. No LangGraph ToolNode involvement — the analyst returns a terminal
AIMessage with zero tool_calls, so the existing conditional edges route
straight to the message-clear node.
"""

import asyncio
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage

from tradingagents.llm_clients.claude_agent_client import ChatClaudeAgent
from tradingagents.llm_clients.mcp_tool_adapter import build_mcp_server


def _build_user_prompt(state: Dict[str, Any]) -> str:
    """Extract any human content from the incoming message sequence.

    Existing analysts rely on LangGraph feeding tool-call round trips through
    state["messages"]. On the SDK path we collapse the incoming messages into a
    single user prompt — tool results are consumed by the SDK loop, not via
    LangGraph, so only the human-authored content matters here.
    """
    parts: List[str] = []
    for msg in state.get("messages", []):
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, str) and content.strip():
                parts.append(content.strip())
    if not parts:
        parts.append("Produce the requested report.")
    return "\n\n".join(parts)


async def _run(
    system_prompt: str,
    user_prompt: str,
    lc_tools: List[Any],
    server_name: str,
    model: str,
) -> str:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        TextBlock,
        query,
    )

    server, allowed = build_mcp_server(server_name, lc_tools)

    options = ClaudeAgentOptions(
        model=model,
        system_prompt=system_prompt,
        mcp_servers={server_name: server},
        allowed_tools=allowed,
        # Block the Claude Code built-ins; only our MCP tools should run.
        disallowed_tools=[
            "Bash", "Read", "Write", "Edit", "MultiEdit",
            "Glob", "Grep", "WebFetch", "WebSearch",
            "Task", "TodoWrite", "NotebookEdit",
        ],
        permission_mode="bypassPermissions",
    )

    text_parts: List[str] = []
    async for msg in query(prompt=user_prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
    return "\n".join(text_parts).strip()


def run_sdk_analyst(
    llm: ChatClaudeAgent,
    state: Dict[str, Any],
    system_prompt: str,
    lc_tools: List[Any],
    server_name: str,
    report_field: str,
) -> Dict[str, Any]:
    """Run an analyst through the Claude Agent SDK tool loop and build the node output."""
    user_prompt = _build_user_prompt(state)
    report = asyncio.run(
        _run(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            lc_tools=lc_tools,
            server_name=server_name,
            model=llm.model,
        )
    )
    return {
        "messages": [AIMessage(content=report)],
        report_field: report,
    }
