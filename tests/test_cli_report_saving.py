from pathlib import Path

from cli.main import (
    resolve_report_save_path,
    save_report_to_disk,
    should_display_report,
    should_save_report,
)


def test_should_save_report_accepts_yes_values():
    assert should_save_report("y") is True
    assert should_save_report("Y") is True
    assert should_save_report("yes") is True
    assert should_save_report(" YES ") is True
    assert should_save_report("") is True
    assert should_save_report(None) is True


def test_should_save_report_rejects_no_values():
    assert should_save_report("n") is False
    assert should_save_report("no") is False
    assert should_save_report("random") is False


def test_should_display_report_uses_same_yes_no_rules():
    assert should_display_report("y") is True
    assert should_display_report("YES") is True
    assert should_display_report("") is True
    assert should_display_report(None) is True
    assert should_display_report("n") is False
    assert should_display_report("no") is False


def test_resolve_report_save_path_uses_default_for_empty_input(tmp_path):
    default_path = tmp_path / "reports" / "SPY_20260529"

    assert resolve_report_save_path("", default_path) == default_path
    assert resolve_report_save_path("   ", default_path) == default_path
    assert resolve_report_save_path(None, default_path) == default_path


def test_resolve_report_save_path_uses_custom_input(tmp_path):
    custom_path = tmp_path / "custom-report-path"
    default_path = tmp_path / "reports" / "SPY_20260529"

    assert resolve_report_save_path(str(custom_path), default_path) == custom_path


def test_save_report_to_disk_writes_complete_report(tmp_path):
    final_state = {
        "market_report": "Market report content",
        "sentiment_report": "Sentiment report content",
        "news_report": "News report content",
        "fundamentals_report": "Fundamentals report content",
        "investment_debate_state": {
            "bull_history": "Bull thesis",
            "bear_history": "Bear thesis",
            "judge_decision": "Research manager decision",
        },
        "trader_investment_plan": "Trader plan",
        "risk_debate_state": {
            "aggressive_history": "Aggressive view",
            "conservative_history": "Conservative view",
            "neutral_history": "Neutral view",
            "judge_decision": "Portfolio decision",
        },
    }

    report_file = save_report_to_disk(final_state, "SPY", tmp_path)

    assert report_file == tmp_path / "complete_report.md"
    assert report_file.exists()

    complete_report = report_file.read_text(encoding="utf-8")

    assert "Trading Analysis Report: SPY" in complete_report
    assert "Market report content" in complete_report
    assert "Research manager decision" in complete_report
    assert "Trader plan" in complete_report
    assert "Portfolio decision" in complete_report

    assert (tmp_path / "1_analysts" / "market.md").exists()
    assert (tmp_path / "2_research" / "manager.md").exists()
    assert (tmp_path / "3_trading" / "trader.md").exists()
    assert (tmp_path / "4_risk" / "neutral.md").exists()
    assert (tmp_path / "5_portfolio" / "decision.md").exists()