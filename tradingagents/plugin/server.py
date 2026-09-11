"""TradingAgents local stdio plugin server."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def prepare_state_root(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=root) as probe:
        probe.write(b"tradingagents")
        probe.flush()
    return root


def create_server() -> FastMCP:
    from mcp.server.fastmcp import FastMCP

    return FastMCP("TradingAgents", log_level="WARNING")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--state-dir",
        default=os.environ.get("TRADINGAGENTS_PLUGIN_STATE_DIR", "~/.tradingagents/plugin/"),
    )
    args = parser.parse_args(argv)

    try:
        prepare_state_root(args.state_dir)
    except OSError as exc:
        print(
            f"Cannot use plugin state directory {args.state_dir}: {exc}. "
            "Set --state-dir to a writable directory.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    try:
        server = create_server()
    except ModuleNotFoundError as exc:
        if exc.name != "mcp":
            raise
        print(
            "Install the plugin runtime with: "
            "python -m pip install 'tradingagents[plugin]'",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
