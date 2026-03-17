---
type: decision
status: active
date: 2026-03-17
agent_author: "claude"
tags: [agents, tools, langgraph, scanner]
related_files: [tradingagents/agents/utils/tool_runner.py]
---

## Context

The existing trading graph uses separate `ToolNode` graph nodes for tool execution (agent -> tool_node -> agent routing loop). Scanner agents are simpler single-pass nodes — no ToolNode in the graph. When the LLM returned tool_calls, nobody executed them, resulting in empty reports.

## The Decision

Created `tradingagents/agents/utils/tool_runner.py` with `run_tool_loop()` that runs an inline tool execution loop within each scanner agent node:
1. Invoke chain
2. If tool_calls present -> execute tools -> append ToolMessages -> re-invoke
3. Repeat up to `MAX_TOOL_ROUNDS=5` until LLM produces text response

Alternative considered: Adding ToolNode + conditional routing to scanner_setup.py (like trading graph). Rejected — too complex for the fan-out/fan-in pattern.

## Constraints

- Trading graph: uses `ToolNode` in graph (do not change).
- Scanner agents: use `run_tool_loop()` inline.

## Actionable Rules

- When an LLM has `bind_tools`, there MUST be a tool execution mechanism — either graph-level `ToolNode` or inline `run_tool_loop()`.
- Always verify the tool execution path exists before marking an agent as complete.
