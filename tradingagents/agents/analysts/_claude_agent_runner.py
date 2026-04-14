"""SDK-native analyst runner.

When the configured LLM is :class:`ChatClaudeAgent`, the analyst node delegates
the whole tool-calling loop to ``claude-agent-sdk``. The SDK owns the loop:
Claude iteratively invokes the translated MCP tools and returns a final text
report. No LangGraph ToolNode involvement — the analyst returns a terminal
AIMessage with zero tool_calls, so the existing conditional edges route
straight to the message-clear node.

Debug logging: set ``TRADINGAGENTS_CLAUDE_AGENT_DEBUG=1`` to log SDK activity
to ``/tmp/tradingagents_claude_agent.log`` (or set
``TRADINGAGENTS_CLAUDE_AGENT_DEBUG=/path/to/file`` for a custom path). Tail it
in a second terminal to watch progress in real time:

    tail -f /tmp/tradingagents_claude_agent.log
"""

import asyncio
import os
import time
from datetime import datetime
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage

from tradingagents.llm_clients.claude_agent_client import ChatClaudeAgent
from tradingagents.llm_clients.mcp_tool_adapter import build_mcp_server


def _debug_path() -> str | None:
    val = os.environ.get("TRADINGAGENTS_CLAUDE_AGENT_DEBUG")
    if not val:
        return None
    if val in ("1", "true", "yes", "on"):
        return "/tmp/tradingagents_claude_agent.log"
    return val


def _log(msg: str) -> None:
    path = _debug_path()
    if not path:
        return
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    try:
        with open(path, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except OSError:
        pass


def _describe_message(msg: Any) -> str:
    """One-line summary of an SDK message for the debug log."""
    try:
        name = type(msg).__name__
        content = getattr(msg, "content", None)
        if content is None:
            return f"{name} (no content)"
        if isinstance(content, list):
            block_summary = []
            for block in content:
                bname = type(block).__name__
                if hasattr(block, "text"):
                    text = str(block.text)
                    snippet = text[:80].replace("\n", " ")
                    block_summary.append(f"{bname}[{len(text)} chars]: {snippet!r}")
                elif hasattr(block, "name"):
                    block_summary.append(f"{bname}(name={block.name!r})")
                else:
                    block_summary.append(bname)
            return f"{name} with {len(content)} blocks: " + " | ".join(block_summary)
        return f"{name}: {str(content)[:200]!r}"
    except Exception as e:
        return f"(failed to describe: {e!r})"


def _build_user_prompt(state: Dict[str, Any]) -> str:
    """Construct a concrete user request from graph state.

    The initial graph state is ``messages = [("human", ticker)]`` — too terse
    for Claude to act on unambiguously, which can leave the SDK session idle
    waiting for clarification. Build an explicit request from
    ``company_of_interest`` + ``trade_date`` so Claude always knows what to do.
    Any additional human-authored content in the message stream is appended.
    """
    ticker = state.get("company_of_interest", "")
    trade_date = state.get("trade_date", "")
    base = (
        f"Produce the requested report for {ticker} as of {trade_date}. "
        "Use the available tools to gather the data you need, then write the "
        "final report. Do not ask clarifying questions — proceed directly."
    ).strip()

    extra: List[str] = []
    for msg in state.get("messages", []):
        content = getattr(msg, "content", None)
        if isinstance(msg, HumanMessage) and isinstance(content, str):
            c = content.strip()
            if c and c != ticker:
                extra.append(c)

    if extra:
        return base + "\n\nAdditional context:\n" + "\n".join(extra)
    return base


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

    _log(f"[{server_name}] building MCP server with {len(lc_tools)} tools: "
         f"{[t.name for t in lc_tools]}")
    server, allowed = build_mcp_server(server_name, lc_tools)
    _log(f"[{server_name}] allowed_tools={allowed}")

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

    _log(f"[{server_name}] starting query(model={model!r}, prompt={user_prompt[:120]!r}...)")
    start = time.monotonic()

    text_parts: List[str] = []
    msg_count = 0
    async for msg in query(prompt=user_prompt, options=options):
        msg_count += 1
        elapsed = time.monotonic() - start
        _log(f"[{server_name}] +{elapsed:.1f}s msg #{msg_count}: {_describe_message(msg)}")
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)

    elapsed = time.monotonic() - start
    _log(f"[{server_name}] query complete after {elapsed:.1f}s, "
         f"{msg_count} messages, {sum(len(t) for t in text_parts)} chars")
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
    _log(f"=== run_sdk_analyst start: server={server_name} report_field={report_field} "
         f"ticker={state.get('company_of_interest')!r} date={state.get('trade_date')!r} ===")
    try:
        report = asyncio.run(
            _run(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                lc_tools=lc_tools,
                server_name=server_name,
                model=llm.model,
            )
        )
    except Exception as e:
        _log(f"[{server_name}] EXCEPTION: {type(e).__name__}: {e}")
        raise
    _log(f"=== run_sdk_analyst done: {report_field}={len(report)} chars ===")
    return {
        "messages": [AIMessage(content=report)],
        report_field: report,
    }
