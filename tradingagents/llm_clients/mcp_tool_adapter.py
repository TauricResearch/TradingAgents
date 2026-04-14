"""Translate LangChain @tool-decorated functions into claude-agent-sdk MCP tools.

LangChain tools expose .name, .description, a Pydantic args_schema, and a sync
.invoke({...}). The SDK wants an @tool-decorated async callable that takes a
dict and returns {"content": [{"type": "text", "text": str}]}.

Used by the SDK-native analyst runner to let Claude Code (authenticated via a
Max/Pro subscription) call the same data tools the legacy analyst path uses.
Callbacks passed in from the graph are forwarded into each tool invocation so
that StatsCallbackHandler (and any other handler) sees on_tool_start/end.
"""

from typing import Any, Dict, List, Optional, Tuple

from claude_agent_sdk import create_sdk_mcp_server, tool


def _wrap_lc_tool(lc_tool: Any, callbacks: Optional[List[Any]]):
    """Wrap a single LangChain BaseTool as an SDK @tool-decorated async callable."""
    schema = (
        lc_tool.args_schema.model_json_schema()
        if lc_tool.args_schema is not None
        else {"type": "object", "properties": {}}
    )
    config = {"callbacks": callbacks} if callbacks else None

    @tool(
        name=lc_tool.name,
        description=lc_tool.description or lc_tool.name,
        input_schema=schema,
    )
    async def _wrapped(args: Dict[str, Any]) -> Dict[str, Any]:
        # Pass callbacks via config so BaseTool fires on_tool_start/on_tool_end.
        result = lc_tool.invoke(args, config=config) if config else lc_tool.invoke(args)
        return {"content": [{"type": "text", "text": str(result)}]}

    return _wrapped


def build_mcp_server(
    server_name: str,
    lc_tools: List[Any],
    callbacks: Optional[List[Any]] = None,
) -> Tuple[Any, List[str]]:
    """Build an in-process MCP server from LangChain tools.

    Returns the server instance and the list of fully-qualified tool names
    (``mcp__<server>__<tool>``) suitable for passing to ``allowed_tools``.

    ``callbacks`` are forwarded into each tool's LangChain config so that
    on_tool_start/on_tool_end fire on the stats handler during SDK-driven
    tool calls.
    """
    wrapped = [_wrap_lc_tool(t, callbacks) for t in lc_tools]
    server = create_sdk_mcp_server(name=server_name, version="1.0.0", tools=wrapped)
    allowed = [f"mcp__{server_name}__{t.name}" for t in lc_tools]
    return server, allowed
