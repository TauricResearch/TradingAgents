from __future__ import annotations

import pytest

from tradingagents.dashboard.extract import build_analysis_record, extract_markdown_label, make_snippet


@pytest.mark.unit
def test_build_analysis_record_parses_final_state(sample_final_state):
    record = build_analysis_record(
        sample_final_state,
        generated_at="2026-04-29T23:00:00+00:00",
        raw_log_path="artifacts/dashboard/raw_results/NVDA/TradingAgentsStrategy_logs/full_states_log_2024-05-10.json",
    )

    assert record["ticker"] == "NVDA"
    assert record["trade_date"] == "2024-05-10"
    assert record["rating"] == "Hold"
    assert record["trader_action"] == "Hold"
    assert record["research_recommendation"] == "Hold"
    assert "Maintain the current NVDA position" in record["decision_summary"]
    assert record["time_horizon"] == "3-6 months"
    assert record["raw_log_path"].endswith("full_states_log_2024-05-10.json")
    assert record["report_lengths"]["final_trade_decision"] > 0
    assert record["snippets"]["market"].startswith("FINAL TRANSACTION PROPOSAL")


@pytest.mark.unit
def test_extract_markdown_label_matches_bold_headers():
    text = "**Rating**: Buy\n\n**Executive Summary**: Add exposure."
    assert extract_markdown_label(text, "Rating") == "Buy"
    assert extract_markdown_label(text, "Executive Summary") == "Add exposure."


@pytest.mark.unit
def test_make_snippet_truncates_long_text():
    text = "word " * 100
    snippet = make_snippet(text, limit=40)
    assert len(snippet) <= 40
    assert snippet.endswith("…")


@pytest.mark.unit
def test_build_analysis_record_serializes_message_like_objects(sample_final_state):
    class DummyMessage:
        def __init__(self, content):
            self.content = content

    sample_final_state = dict(sample_final_state)
    sample_final_state["messages"] = [DummyMessage("hello")]

    record = build_analysis_record(sample_final_state)

    assert record["raw_state"]["messages"][0]["content"] == "hello"


@pytest.mark.unit
def test_build_analysis_record_uses_trader_plan_fallback(sample_final_state):
    sample_final_state = dict(sample_final_state)
    sample_final_state.pop("trader_investment_decision")
    sample_final_state["trader_investment_plan"] = "**Action**: Buy\n\n**Reasoning**: Test fallback."

    record = build_analysis_record(sample_final_state)

    assert record["trader_action"] == "Buy"
    assert record["reports"]["trader_investment_decision"].startswith("**Action**: Buy")


@pytest.mark.unit
def test_build_analysis_record_sanitizes_mixed_script_artifacts(sample_final_state):
    sample_final_state = dict(sample_final_state)
    sample_final_state["fundamentals_report"] = "# NVDA фундаментал 분석 보고서\n핵심은 좋다."
    sample_final_state["investment_plan"] = (
        "**Recommendation**: Overweight\n\n"
        "**Rationale**: 여전히 бул(강세) 논리 우위.\n\n"
        "**Strategic Actions**: 분할 매수."
    )
    sample_final_state["risk_debate_state"] = {
        **sample_final_state["risk_debate_state"],
        "judge_decision": "**Rating**: Overweight\n\n**Executive Summary**: фундаментals 개선 + बुल 논리 유지.",
    }

    record = build_analysis_record(sample_final_state)

    assert "фундамент" not in record["reports"]["fundamentals_report"]
    assert "бул" not in record["reports"]["investment_plan"]
    assert "बुल" not in record["decision_summary"]
    assert "펀더멘털" in record["reports"]["fundamentals_report"]
    assert "강세" in record["reports"]["investment_plan"]
    assert "펀더멘털" in record["raw_state"]["fundamentals_report"]
