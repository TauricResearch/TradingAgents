"""Report parity: the shared writer produces the report tree for the CLI and the
programmatic API alike (#1037)."""

import re
from types import SimpleNamespace

import pytest

from cli.report_fields import MissingPriceTargetError
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import report_settings, write_report_tree


def _state():
    return {
        "market_report": "MKT",
        "news_report": "NEWS",
        "investment_debate_state": {"bull_history": "BULL"},
        "investment_plan": "RM PLAN",
        "trader_investment_plan": "TRADE",
        "risk_debate_state": {"neutral_history": "NEUTRAL"},
        "final_trade_decision": "PM DECISION\n**Price Target**: 120",
    }


SETTINGS = {"version": "0.5.2", "llm_provider": "openai", "deep_think_llm": "gpt-6-sol",
            "quick_think_llm": "gpt-6-luna", "analysts": ["market", "news"], "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 2, "data_vendors": {"core_stock_apis": "yfinance"}}


@pytest.mark.unit
def test_write_report_tree_creates_files(tmp_path):
    out = write_report_tree(_state(), "AAPL", tmp_path)
    assert out.name == "complete_report.md"
    assert (tmp_path / "1_analysts" / "market.md").read_text() == "MKT"
    assert (tmp_path / "1_analysts" / "news.md").read_text() == "NEWS"
    assert (tmp_path / "2_research" / "manager.md").read_text() == "RM PLAN"
    assert (tmp_path / "3_trading" / "trader.md").read_text() == "TRADE"
    assert (tmp_path / "5_portfolio" / "decision.md").read_text() == "PM DECISION\n**Price Target**: 120"
    complete = out.read_text()
    assert "Trading Analysis Report: AAPL" in complete
    assert "MKT" in complete and "PM DECISION\n**Price Target**: 120" in complete


@pytest.mark.unit
def test_save_reports_explicit_path(tmp_path):
    graph = SimpleNamespace(run_settings=lambda: SETTINGS)
    out = TradingAgentsGraph.save_reports(graph, _state(), "AAPL", save_path=tmp_path)
    assert (tmp_path / "complete_report.md").exists()
    assert out == tmp_path / "complete_report.md"


@pytest.mark.unit
def test_save_reports_defaults_under_results_dir(tmp_path):
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"results_dir": str(tmp_path)}
    graph.run_settings = lambda: SETTINGS
    out = graph.save_reports(_state(), "AAPL")
    assert out.exists()
    assert out.parent.parent.name == "reports"  # results_dir/reports/AAPL_<stamp>/...
    assert out.parent.name.startswith("AAPL_")


@pytest.mark.parametrize("target", ["not provided", "n/a", "0", "-10", "NaN", "inf", "10%", "100-120",
                                   "6 months", "20 basis points"])
def test_incomplete_decision_is_not_saved(tmp_path, target):
    state = _state()
    state["final_trade_decision"] = f"**Price Target**: {target}"
    destination = tmp_path / "new-report"
    with pytest.raises(MissingPriceTargetError):
        write_report_tree(state, "AAPL", destination)
    assert not destination.exists()


@pytest.mark.unit
def test_the_report_names_the_analysis_date_and_what_produced_it(tmp_path):
    state = dict(_state(), trade_date="2026-09-23")

    header = write_report_tree(state, "NVDA", tmp_path, settings=SETTINGS).read_text().split("## ")[0]

    assert "Analysis date: 2026-09-23" in header
    assert "TradingAgents 0.5.2" in header
    assert "openai, deep gpt-6-sol, quick gpt-6-luna" in header
    assert "Analysts: market, news" in header
    assert "research debate rounds 1, risk debate rounds 2" in header
    assert "core_stock_apis yfinance" in header


@pytest.mark.unit
def test_run_settings_record_the_run_without_endpoints_or_paths():
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.selected_analysts = ("market", "news")
    graph.config = {"llm_provider": "openai", "deep_think_llm": "gpt-6-sol", "quick_think_llm": "gpt-6-luna",
                    "max_debate_rounds": 1, "max_risk_discuss_rounds": 1, "output_language": "English",
                    "data_vendors": {"core_stock_apis": "yfinance"}, "tool_vendors": {},
                    "backend_url": "https://user:secret@relay.example/v1", "results_dir": "/home/me/results"}

    settings = graph.run_settings()

    assert settings["analysts"] == ["market", "news"]
    assert settings["deep_think_llm"] == "gpt-6-sol"
    assert "secret" not in str(settings) and "/home/me" not in str(settings)


@pytest.mark.unit
def test_a_partial_settings_dict_still_writes_the_report(tmp_path):
    out = write_report_tree(_state(), "AAPL", tmp_path, settings={"llm_provider": "openai"})
    assert "openai" in out.read_text()


@pytest.mark.unit
def test_run_settings_name_the_version_of_the_running_code():
    import tradingagents
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.selected_analysts, graph.config = ("market",), {}
    assert graph.run_settings()["version"] == tradingagents.__version__


@pytest.mark.unit
@pytest.mark.parametrize("decision, rating", [
    ("**Rating**: Overweight\n**Price Target**: 120\n\nAdd on weakness.", "Overweight"),
    ("Add on weakness.\n**Price Target**: 120", "REVIEW"),           # no readable rating is said, not left out
])
def test_the_report_header_names_the_rating(tmp_path, decision, rating):
    state = dict(_state(), final_trade_decision=decision)

    header = write_report_tree(state, "NVDA", tmp_path, settings=SETTINGS).read_text().split("## ")[0]

    assert f"- Rating: {rating}" in header


@pytest.mark.unit
def test_the_header_names_the_analysts_as_users_select_them(tmp_path):
    settings = {**SETTINGS, "analysts": ["market", "social", "news"]}

    write_report_tree(_state(), "NVDA", tmp_path, settings=settings, html=True)

    markdown = (tmp_path / "complete_report.md").read_text(encoding="utf-8")
    assert "market, sentiment, news" in markdown and "social" not in markdown
    page = (tmp_path / "complete_report.html").read_text(encoding="utf-8")
    fields = re.findall(r'<span class="field">([^<]*)</span>', page)
    assert {"market", "sentiment", "news"} <= set(fields) and "social" not in page


@pytest.mark.unit
def test_report_settings_allowlists_metadata_for_graph_and_batch_runs():
    import tradingagents

    config = {
        "llm_provider": "openai", "deep_think_provider": "anthropic",
        "deep_think_llm": "claude-opus-4-8", "quick_think_llm": "gpt-5.5",
        "max_debate_rounds": 3, "max_risk_discuss_rounds": 2, "output_language": "English",
        "data_vendors": {"news_data": "yfinance"}, "tool_vendors": {"get_news": "alpha_vantage"},
        "backend_url": "https://user:secret@relay.example/v1",
        "deep_think_backend_url": "https://user:secret@another.example",
        "api_key": "secret", "reports_dir": "/private/reports", "results_dir": "/private/results",
    }
    analysts = ["market", "social"]

    settings = report_settings(config, analysts)

    assert settings == {
        "version": tradingagents.__version__, "llm_provider": "openai",
        "deep_think_provider": "anthropic", "deep_think_llm": "claude-opus-4-8",
        "quick_think_provider": "openai", "quick_think_llm": "gpt-5.5",
        "analysts": ["market", "social"], "max_debate_rounds": 3,
        "max_risk_discuss_rounds": 2, "output_language": "English",
        "data_vendors": {"news_data": "yfinance"}, "tool_vendors": {"get_news": "alpha_vantage"},
    }
    assert "secret" not in str(settings) and "/private/" not in str(settings)
    settings["analysts"].append("news")
    settings["data_vendors"]["news_data"] = "other"
    settings["tool_vendors"]["get_news"] = "other"
    assert analysts == ["market", "social"]
    assert config["data_vendors"] == {"news_data": "yfinance"}
    assert config["tool_vendors"] == {"get_news": "alpha_vantage"}


@pytest.mark.unit
@pytest.mark.parametrize("normalize", [False, True])
def test_heading_normalization_is_optional_and_preserves_agent_stage_files(tmp_path, normalize):
    body = "# View\n## Trend\n### Detail\n#### Existing\n```markdown\n## Code\n```\n"
    state = dict(_state(), market_report=body)

    report = write_report_tree(state, "AAPL", tmp_path, html=False,
                               normalize_headings=normalize).read_text(encoding="utf-8")

    expected = ("#### View\n#### Trend\n#### Detail\n#### Existing\n" if normalize else
                "# View\n## Trend\n### Detail\n#### Existing\n")
    assert f"### Market Analyst\n{expected}```markdown\n## Code\n```\n" in report
    assert (tmp_path / "1_analysts" / "market.md").read_text(encoding="utf-8") == body
