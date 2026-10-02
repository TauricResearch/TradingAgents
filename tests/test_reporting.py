"""Report parity: the shared writer produces the report tree for the CLI and the
programmatic API alike (#1037)."""

from types import SimpleNamespace

import pytest

from cli.report_fields import MissingPriceTargetError
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import write_report_tree


def _state():
    return {
        "market_report": "MKT",
        "news_report": "NEWS",
        "investment_debate_state": {"judge_decision": "RM PLAN"},
        "trader_investment_plan": "TRADE",
        "risk_debate_state": {"judge_decision": "PM DECISION\n**Price Target**: 120"},
    }


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
    # Unbound: with an explicit save_path, the method doesn't touch self/config.
    out = TradingAgentsGraph.save_reports(None, _state(), "AAPL", save_path=tmp_path)
    assert (tmp_path / "complete_report.md").exists()
    assert out == tmp_path / "complete_report.md"


@pytest.mark.unit
def test_save_reports_defaults_under_results_dir(tmp_path):
    mock_self = SimpleNamespace(config={"results_dir": str(tmp_path)})
    out = TradingAgentsGraph.save_reports(mock_self, _state(), "AAPL")
    assert out.exists()
    assert out.parent.parent.name == "reports"  # results_dir/reports/AAPL_<stamp>/...
    assert out.parent.name.startswith("AAPL_")


@pytest.mark.parametrize("target", ["not provided", "n/a", "0", "-10", "NaN", "inf", "10%", "100-120",
                                   "6 months", "20 basis points"])
def test_incomplete_decision_is_not_saved(tmp_path, target):
    state = _state()
    state["risk_debate_state"]["judge_decision"] = f"**Price Target**: {target}"
    state["final_trade_decision"] = "Price Target: 120"  # This is not what the writer saves.
    destination = tmp_path / "new-report"
    with pytest.raises(MissingPriceTargetError):
        write_report_tree(state, "AAPL", destination)
    assert not destination.exists()
