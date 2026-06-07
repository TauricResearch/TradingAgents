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
        "india_market_report": "Market section\n\nSource: NSE\nData Quality: medium\nConfidence: medium",
        "india_fundamentals_report": "Fundamentals section\n\nSource: local filing\nData Quality: high\nConfidence: medium",
        "india_news_filings_report": "News section\n\nSources: BSE announcements\nData Quality: medium\nConfidence: medium",
        "india_macro_policy_report": "Macro section\n\nUNAVAILABLE: official macro datapoint missing.",
        "india_flows_report": "Flows section\n\nUNAVAILABLE: FII/DII data missing.",
        "india_compliance_report": "Compliance section",
        "trader_investment_plan": "Trader model view: Hold",
        "final_trade_decision": "Model view: Hold",
        "investment_debate_state": {"bull_history": "Bull", "bear_history": "Bear", "judge_decision": "Manager"},
        "risk_debate_state": {"aggressive_history": "Aggressive", "conservative_history": "Conservative", "neutral_history": "Neutral"},
    }
    report = save_report_to_disk(final_state, "RELIANCE.NS", tmp_path)
    assert report.exists()
    complete_report = report.read_text(encoding="utf-8")
    assert INDIA_COMPLIANCE_DISCLAIMER in complete_report
    assert "## Data Quality And Source Coverage" in complete_report
    assert "Trader Research View" in complete_report
    assert (tmp_path / "disclaimer.md").exists()
    assert (tmp_path / "trader_research_view.md").exists()
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["symbol"] == "RELIANCE.NS"
    assert summary["section_files"]["Trader Research View"] == "trader_research_view.md"


@pytest.mark.unit
def test_report_writer_adds_disclaimer_and_artifact_notes_to_section_files(tmp_path):
    final_state = {
        "trade_date": "2026-06-05",
        "india_market_report": "Source: NSE\nData Quality: medium\nConfidence: medium\nMarket section",
        "final_trade_decision": "Model view: Hold",
    }
    save_report_to_disk(final_state, "RELIANCE.NS", tmp_path)

    section = (tmp_path / "1_market_technical.md").read_text(encoding="utf-8")
    assert "## Compliance Disclaimer" in section
    assert INDIA_COMPLIANCE_DISCLAIMER in section
    assert "## Report Artifact Notes" in section
    assert "Source coverage detected in section text: Yes" in section
    assert "Data-quality coverage detected in section text: Yes" in section
    assert "Confidence coverage detected in section text: Yes" in section
    assert "writer-level coverage checks only" in section


@pytest.mark.unit
def test_report_writer_indexes_sources_and_data_quality_coverage(tmp_path):
    final_state = {
        "trade_date": "2026-06-05",
        "india_market_report": "Source: NSE\nData Quality: medium\nConfidence: medium\nMarket section",
        "india_macro_policy_report": "UNAVAILABLE: official macro datapoint missing.",
        "final_trade_decision": "Model view: Hold",
    }
    save_report_to_disk(final_state, "RELIANCE.NS", tmp_path)

    data_quality = json.loads((tmp_path / "data_quality.json").read_text(encoding="utf-8"))
    market = data_quality["sections"]["India Market Technical"]
    macro = data_quality["sections"]["India Macro & Policy"]
    flows = data_quality["sections"]["India Flows & Positioning"]

    assert data_quality["coverage_method"] == "writer_marker_detection_only"
    assert market["source_coverage_detected"] is True
    assert market["data_quality_detected"] is True
    assert market["confidence_detected"] is True
    assert macro["contains_unavailable_marker"] is True
    assert flows["status"] == "unavailable"
    assert "Section was not produced in the current run." in flows["warnings"]

    sources = (tmp_path / "sources.md").read_text(encoding="utf-8")
    assert "# Sources And Data Quality Coverage" in sources
    assert "| India Market Technical | 1_market_technical.md | available | Yes | Yes | Yes | No |" in sources
    assert "Section text does not include explicit source coverage." in sources


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
