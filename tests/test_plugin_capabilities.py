import importlib
import os
import subprocess
import sys
from types import ModuleType

import pytest


def test_credentials_are_presence_only(monkeypatch):
    from tradingagents.plugin.server import (
        AnalysisSettings,
        Capabilities,
        DataSourceCapability,
        RoleCapability,
        get_capabilities,
    )

    monkeypatch.setenv("FRED_API_KEY", "secret-sentinel-123")
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)

    result = get_capabilities()

    assert result.data_sources["fred"].credential_present is True
    assert result.data_sources["alpha_vantage"].credential_present is False
    assert "secret-sentinel-123" not in result.model_dump_json()
    assert result.available_tools == ["get_capabilities"]
    assert result.planned_data_tools == [
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
    ]
    assert result.api_runner_settings == [
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
    ]
    assert set(result.data_sources) == {
        "alpha_vantage",
        "fred",
        "yfinance",
        "polymarket",
        "stocktwits",
        "reddit",
    }
    assert all(
        result.data_sources[name].credential_env is None
        and result.data_sources[name].credential_present is None
        for name in ("yfinance", "polymarket", "stocktwits", "reddit")
    )
    assert result.schema_version == 1
    assert result.analysis_settings.available is False
    assert result.analysis_settings.model_dump() == {
        "available": False,
        "asset_types": ["stock", "crypto"],
        "analysts": ["market", "social", "news", "fundamentals"],
        "debate_rounds": 1,
        "risk_rounds": 1,
        "output_language": "English",
        "vendor_selection": "ordered category and per-tool overrides",
    }
    assert all(
        model.model_config.get("extra") == "forbid"
        for model in (RoleCapability, AnalysisSettings, DataSourceCapability, Capabilities)
    )
    assert [role.key for role in result.roles[:4]] == [
        "market",
        "social",
        "news",
        "fundamentals",
    ]
    assert result.roles[1].label == "Sentiment Analyst"
    assert all(not role.workflow_available for role in result.roles)


def test_empty_and_unrelated_credentials_are_not_discovered(monkeypatch):
    from tradingagents.plugin.server import get_capabilities

    monkeypatch.setenv("FRED_API_KEY", "")
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.setenv("UNRELATED_SECRET", "unrelated-secret-sentinel")

    result = get_capabilities()

    assert result.data_sources["fred"].credential_present is False
    assert result.data_sources["alpha_vantage"].credential_present is False
    assert "unrelated-secret-sentinel" not in result.model_dump_json()


def test_graph_exports_are_lazy_and_cached():
    import tradingagents.graph as graph

    exports = {
        "TradingAgentsGraph": "trading_graph",
        "ConditionalLogic": "conditional_logic",
        "GraphSetup": "setup",
        "Propagator": "propagation",
        "Reflector": "reflection",
        "SignalProcessor": "signal_processing",
    }

    for name, module_name in exports.items():
        value = getattr(graph, name)
        module = importlib.import_module(f"tradingagents.graph.{module_name}")
        assert value is getattr(module, name)
        assert getattr(graph, name) is value

    with pytest.raises(AttributeError, match="has no attribute 'missing'"):
        _ = graph.missing


def test_discovery_does_not_call_network_or_runner(monkeypatch):
    import socket

    from tradingagents.plugin.server import get_capabilities

    monkeypatch.setattr(socket.socket, "connect", lambda *_: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(
        "tradingagents.llm_clients.factory.create_llm_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()),
    )

    assert get_capabilities().model_dump_json()


def test_create_server_registers_capability_tool(monkeypatch):
    from tradingagents.plugin.server import create_server, get_capabilities

    registered = []

    class FakeFastMCP:
        def __init__(self, *_args, **_kwargs):
            pass

        def tool(self):
            return registered.append

    mcp = ModuleType("mcp")
    server = ModuleType("mcp.server")
    fastmcp = ModuleType("mcp.server.fastmcp")
    fastmcp.FastMCP = FakeFastMCP
    monkeypatch.setitem(sys.modules, "mcp", mcp)
    monkeypatch.setitem(sys.modules, "mcp.server", server)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fastmcp)

    assert isinstance(create_server(), FakeFastMCP)
    assert registered == [get_capabilities]


def test_discovery_imports_without_runner_or_global_config(tmp_path):
    code = '''\
import sys
from tradingagents.plugin.server import get_capabilities
assert get_capabilities().available_tools == ["get_capabilities"]
assert "tradingagents.graph.trading_graph" not in sys.modules
assert "tradingagents.default_config" not in sys.modules
assert "tradingagents.llm_clients.factory" not in sys.modules
'''
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["TRADINGAGENTS_TEMPERATURE"] = "invalid-for-api"

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
