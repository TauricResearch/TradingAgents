"""Model Context Protocol server for TradingAgents.

Install the optional dependency with ``pip install "tradingagents[mcp]"`` and
run ``tradingagents-mcp``. The server speaks stdio by default, so MCP clients
such as Claude Code, Codex, and Antigravity can launch it as a local process.
"""

from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    """Run the MCP server, reporting a missing optional dependency clearly."""
    from tradingagents.mcp.cli import main as cli_main

    return cli_main(argv)
