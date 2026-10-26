"""Command-line entry point for the TradingAgents MCP server."""

from __future__ import annotations

import argparse
import logging
import sys

import tradingagents


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tradingagents-mcp",
        description="Run TradingAgents as a Model Context Protocol server.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http", "sse"),
        default="stdio",
        help="MCP transport (default: stdio, which MCP clients launch directly).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address for the HTTP transports (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for the HTTP transports (default: 8000).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        help="Log level written to stderr (default: INFO).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable FastMCP debug logging.",
    )
    parser.add_argument("--version", action="version", version=tradingagents.__version__)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        stream=sys.stderr,
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        from tradingagents.mcp.server import create_server
    except ModuleNotFoundError as exc:
        if exc.name != "mcp" and not (exc.name or "").startswith("mcp."):
            raise
        print(
            'The TradingAgents MCP server needs the "mcp" extra: pip install "tradingagents[mcp]"',
            file=sys.stderr,
        )
        return 2

    if args.transport != "stdio" and args.host not in {"127.0.0.1", "localhost", "::1"}:
        logging.getLogger(__name__).warning(
            "The HTTP transports have no authentication; keep --host on loopback "
            "or put the server behind an authenticated proxy."
        )

    server = create_server(
        host=args.host,
        port=args.port,
        debug=args.debug,
        log_level=args.log_level,
    )
    server.run(transport=args.transport)
    return 0
