import json
import tomllib
from pathlib import Path

import pytest
import typer

from cli import main as cli_main
from cli.main import INDIA_COMPLIANCE_DISCLAIMER, run_doctor_checks, save_report_to_disk
from tradingagents.dataflows.india.symbols import IndiaSymbolError


@pytest.mark.unit
def test_doctor_validates_india_ticker():
    checks = run_doctor_checks("RELIANCE")
    assert checks["ticker_validation"] == "RELIANCE.NS"
    assert checks["package_import"] is True


@pytest.mark.unit
def test_report_writer_creates_disclaimer_and_summary(tmp_path):
    final_state = {
        "trade_date": "2026-06-05",
        "india_market_report": "Market section",
        "india_fundamentals_report": "Fundamentals section",
        "india_news_filings_report": "News section",
        "india_macro_policy_report": "Macro section",
        "india_flows_report": "Flows section",
        "india_compliance_report": "Compliance section",
        "final_trade_decision": "Model view: Hold",
        "investment_debate_state": {"bull_history": "Bull", "bear_history": "Bear", "judge_decision": "Manager"},
        "risk_debate_state": {"aggressive_history": "Aggressive", "conservative_history": "Conservative", "neutral_history": "Neutral"},
    }
    report = save_report_to_disk(final_state, "RELIANCE.NS", tmp_path)
    assert report.exists()
    assert INDIA_COMPLIANCE_DISCLAIMER in report.read_text(encoding="utf-8")
    assert (tmp_path / "disclaimer.md").exists()
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["symbol"] == "RELIANCE.NS"


@pytest.mark.unit
def test_report_writer_rejects_unsafe_ticker_component(tmp_path):
    with pytest.raises(IndiaSymbolError):
        save_report_to_disk({"trade_date": "2026-06-05"}, "../RELIANCE", tmp_path)


@pytest.mark.unit
def test_default_report_path_uses_safe_india_ticker(monkeypatch, tmp_path):
    captured = {}

    def fake_graph_factory(selected_analysts, config, debug):
        class FakeGraph:
            def propagate(self, ticker, trade_date):
                captured["ticker"] = ticker
                captured["trade_date"] = trade_date
                return (
                    {
                        "trade_date": trade_date,
                        "india_market_report": "Market section",
                        "final_trade_decision": "Model view: Hold",
                    },
                    "Hold",
                )

        return FakeGraph()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_main, "TradingAgentsGraph", fake_graph_factory)
    monkeypatch.setattr(cli_main, "get_api_key_env", lambda provider: None)

    decision = cli_main.run_noninteractive_analysis(
        ticker="RELIANCE",
        analysis_date="2026-06-05",
        analysts="india_market",
        provider="openai",
        quick_model=None,
        deep_model=None,
        research_depth=1,
        checkpoint=False,
        save_path=None,
        no_display=True,
        no_save_prompt=True,
    )

    assert decision == "Hold"
    assert captured == {"ticker": "RELIANCE.NS", "trade_date": "2026-06-05"}
    assert (tmp_path / "reports" / "RELIANCE.NS" / "2026-06-05" / "complete_report.md").exists()


@pytest.mark.unit
def test_cli_metadata_is_rebranded_and_keeps_legacy_entrypoint():
    repo_root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert "IndiaMarketAgents" in project["description"]
    assert project["scripts"]["indiamarketagents"] == "cli.main:app"
    assert project["scripts"]["tradingagents"] == "cli.main:app"
    assert isinstance(cli_main.app, typer.Typer)
