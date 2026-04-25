from pathlib import Path

from agent_os.backend.services.report_helpers import (
    format_report_section_for_persistence,
    sanitize_report_text_for_persistence,
    write_complete_report_md,
)


def test_sanitize_report_text_for_persistence_drops_prompt_leak_lines():
    text = """
We need to analyze the latest data.
You are a researcher tasked with performing deep fundamental analysis.
- AAPL held support at $190.25 and momentum improved.
## Scanner Context
This should not be persisted.
"""

    cleaned = sanitize_report_text_for_persistence(text)

    assert "We need to analyze" not in cleaned
    assert "You are a researcher" not in cleaned
    assert "Scanner Context" not in cleaned
    assert "AAPL held support" in cleaned


def test_write_complete_report_md_sanitizes_sections(tmp_path: Path):
    final_state = {
        "market_report": "We need to analyze the latest data.\n- AAPL held support at $190.25.",
        "news_report": "AAPL News Analysis\n\n- AAPL demand improved 8%.",
        "fundamentals_report": "You are a researcher tasked with performing deep fundamental analysis.\n- AAPL margins expanded.",
        "investment_plan": "We need to follow instruction.\nStrongest Bull Evidence:\n- AAPL revenue held at $10.00.\nRecommendation:\n- HOLD.",
    }

    write_complete_report_md(final_state, "AAPL", tmp_path)
    report = (tmp_path / "complete_report.md").read_text(encoding="utf-8")

    assert "We need to analyze" not in report
    assert "You are a researcher" not in report
    assert "We need to follow instruction" not in report
    assert "Strongest Bull Evidence:" not in report
    assert "AAPL held support at $190.25." in report
    assert "AAPL News Analysis" in report
    assert "- AAPL revenue held at $10.00." in report


def test_format_report_section_for_persistence_extracts_final_decision_bullets():
    text = """
We need to follow instruction.
- $4.1B Sealed Air Loan. Could format as $4.10B?
Strongest Bull Evidence:
- $4.10B Sealed Air Loan demonstrates lending capacity.
Recommendation:
- HOLD.
Strategic Actions:
- Wait for better price data.
"""

    cleaned = format_report_section_for_persistence("investment_plan", text)

    assert "We need to follow instruction" not in cleaned
    assert "Could format as" not in cleaned
    assert cleaned == (
        "- $4.10B Sealed Air Loan demonstrates lending capacity.\n"
        "- HOLD.\n"
        "- Wait for better price data."
    )


def test_format_report_section_for_persistence_renders_market_json():
    text = """
{"timeframe":"1 month","executive_summary":"Energy premium remains elevated.","key_themes":[{"theme":"Energy","description":"WTI rose to $112.06.","conviction":"high","timeframe":"1 month"}],"stocks_to_investigate":[{"ticker":"JPM","rationale":"Financial earnings catalyst.","conviction":"high","key_catalysts":["2026-04-14"],"risks":["credit"]}]}
"""

    cleaned = format_report_section_for_persistence("market_report", text)

    assert "- Timeframe: 1 month" in cleaned
    assert "- Executive Summary: Energy premium remains elevated." in cleaned
    assert "- Theme: Energy | WTI rose to $112.06.; conviction=high; timeframe=1 month" in cleaned
    assert (
        "- Candidate: JPM | Financial earnings catalyst.; conviction=high; catalysts=1; risks=1"
        in cleaned
    )
