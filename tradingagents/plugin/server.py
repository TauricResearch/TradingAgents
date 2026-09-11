"""TradingAgents local stdio plugin server."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


class RoleCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    workflow_available: bool = False


class AnalysisSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool = False
    asset_types: list[str]
    analysts: list[str]
    debate_rounds: int = 1
    risk_rounds: int = 1
    output_language: str = "English"
    vendor_selection: str = "ordered category and per-tool overrides"


class DataSourceCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential_env: str | None
    credential_present: bool | None
    note: str


class Capabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_version: str
    schema_version: int = 1
    mcp_sdk_version: str | None
    available_tools: list[str]
    planned_data_tools: list[str]
    roles: list[RoleCapability]
    analysis_settings: AnalysisSettings
    data_sources: dict[str, DataSourceCapability]
    api_runner_settings: list[str]
    reasoning_host: str = "Codex session; API-runner settings do not configure it"


def _distribution_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def get_capabilities() -> Capabilities:
    """Describe the local plugin without loading the analysis runner."""
    from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS

    roles = [
        RoleCapability(key=spec.key, label=spec.agent_node)
        for spec in ANALYST_NODE_SPECS.values()
    ]
    roles.extend(
        RoleCapability(key=key, label=label)
        for key, label in (
            ("bull", "Bull Analyst"),
            ("bear", "Bear Analyst"),
            ("research_manager", "Research Manager"),
            ("trader", "Trader"),
            ("aggressive", "Aggressive Analyst"),
            ("conservative", "Conservative Analyst"),
            ("neutral", "Neutral Analyst"),
            ("portfolio_manager", "Portfolio Manager"),
            ("reflection", "Reflection"),
        )
    )

    def keyed_source(credential_env: str) -> DataSourceCapability:
        return DataSourceCapability(
            credential_env=credential_env,
            credential_present=bool(os.environ.get(credential_env)),
            note="Credential presence is not validity.",
        )

    keyless_source = DataSourceCapability(
        credential_env=None,
        credential_present=None,
        note="Keyless availability is not guaranteed.",
    )
    return Capabilities(
        runtime_version=version("tradingagents"),
        mcp_sdk_version=_distribution_version("mcp"),
        available_tools=["get_capabilities"],
        planned_data_tools=[
            "get_stock_data",
            "get_indicators",
            "get_verified_market_snapshot",
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement",
            "get_news",
            "get_global_news",
            "get_insider_transactions",
            "get_macro_indicators",
            "get_prediction_markets",
            "resolve_instrument_identity",
            "fetch_stocktwits_messages",
            "fetch_reddit_posts",
            "get_decision_history",
        ],
        roles=roles,
        analysis_settings=AnalysisSettings(
            asset_types=["stock", "crypto"],
            analysts=list(ANALYST_NODE_SPECS),
        ),
        data_sources={
            "alpha_vantage": keyed_source("ALPHA_VANTAGE_API_KEY"),
            "fred": keyed_source("FRED_API_KEY"),
            "yfinance": keyless_source,
            "polymarket": keyless_source,
            "stocktwits": keyless_source,
            "reddit": keyless_source,
        },
        api_runner_settings=[
            "llm_provider",
            "deep_think_llm",
            "quick_think_llm",
            "backend_url",
            "temperature",
            "llm_max_retries",
            "max_tokens",
            "google_thinking_level",
            "openai_reasoning_effort",
            "anthropic_effort",
        ],
    )


def prepare_state_root(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=root) as probe:
        probe.write(b"tradingagents")
        probe.flush()
    return root


def create_server() -> FastMCP:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("TradingAgents", log_level="WARNING")
    server.tool()(get_capabilities)
    return server


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
