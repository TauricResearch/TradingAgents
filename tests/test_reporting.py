"""Report parity: the shared writer produces the report tree for the CLI and the
programmatic API alike (#1037)."""

import json
from types import SimpleNamespace

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import write_report_tree
from tradingagents.run_manifest import build_run_manifest


def _state():
    return {
        "market_report": "MKT",
        "news_report": "NEWS",
        "investment_debate_state": {"judge_decision": "RM PLAN"},
        "trader_investment_plan": "TRADE",
        "risk_debate_state": {"judge_decision": "PM DECISION"},
    }


@pytest.mark.unit
def test_write_report_tree_creates_files(tmp_path):
    out = write_report_tree(_state(), "AAPL", tmp_path)
    assert out.name == "complete_report.md"
    assert (tmp_path / "1_analysts" / "market.md").read_text() == "MKT"
    assert (tmp_path / "1_analysts" / "news.md").read_text() == "NEWS"
    assert (tmp_path / "2_research" / "manager.md").read_text() == "RM PLAN"
    assert (tmp_path / "3_trading" / "trader.md").read_text() == "TRADE"
    assert (tmp_path / "5_portfolio" / "decision.md").read_text() == "PM DECISION"
    complete = out.read_text()
    assert "Trading Analysis Report: AAPL" in complete
    assert "MKT" in complete and "PM DECISION" in complete


@pytest.mark.unit
def test_write_report_tree_writes_supplied_manifest(tmp_path):
    manifest = {"schema_version": "1", "run": {"ticker": "AAPL"}}
    write_report_tree(_state(), "AAPL", tmp_path, run_manifest=manifest)

    assert json.loads((tmp_path / "run_manifest.json").read_text()) == manifest


@pytest.mark.unit
def test_run_manifest_is_deterministic_and_excludes_runtime_paths(tmp_path):
    config = {
        "llm_provider": "openai",
        "deep_think_llm": "deep-model",
        "quick_think_llm": "quick-model",
        "backend_url": "https://user:secret@example.test/v1?api_key=secret",
        "temperature": 0.0,
        "data_vendors": {"core_stock_apis": "yfinance,alpha_vantage"},
        "tool_vendors": {"get_news": "yfinance"},
        "results_dir": str(tmp_path),
    }
    state = {
        "trade_date": "2026-01-15",
        "asset_type": "stock",
        "instrument_context": "Apple Inc. (AAPL)",
        "past_context": "prior run",
        "final_trade_decision": "**Rating**: Buy",
    }

    first = build_run_manifest(config, state, "AAPL", ["market", "news"])
    config["results_dir"] = str(tmp_path / "somewhere-else")
    second = build_run_manifest(config, state, "AAPL", ["market", "news"])

    assert first == second
    assert first["configuration"]["backend_url"] == "https://example.test/v1"
    assert first["configured_data_sources"]["category_vendor_ids"] == {
        "core_stock_apis": "yfinance,alpha_vantage",
    }
    assert first["run"]["requested_as_of"] == "2026-01-15"
    assert first["output"]["final_rating"] == "Buy"
    serialized = json.dumps(first)
    assert "secret" not in serialized
    assert str(tmp_path) not in serialized


@pytest.mark.unit
def test_save_reports_explicit_path(tmp_path):
    # Unbound: with an explicit save_path, the method doesn't touch self/config.
    out = TradingAgentsGraph.save_reports(None, _state(), "AAPL", save_path=tmp_path)
    assert (tmp_path / "complete_report.md").exists()
    assert out == tmp_path / "complete_report.md"


@pytest.mark.unit
def test_save_reports_defaults_under_results_dir(tmp_path):
    mock_self = SimpleNamespace(
        config={
            "results_dir": str(tmp_path),
            "llm_provider": "openai",
            "data_vendors": {"core_stock_apis": "yfinance"},
        },
        selected_analysts=("market",),
    )
    out = TradingAgentsGraph.save_reports(mock_self, _state(), "AAPL")
    assert out.exists()
    assert out.parent.parent.name == "reports"  # results_dir/reports/AAPL_<stamp>/...
    assert out.parent.name.startswith("AAPL_")
    manifest = json.loads((out.parent / "run_manifest.json").read_text())
    assert manifest["run"]["selected_analysts"] == ["market"]
