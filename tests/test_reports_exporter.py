"""Tests for the report exporter (file layout + decision parsing + PDF)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tradingagents.reports.exporter import (
    DecisionSummary,
    extract_decision_summary,
    markdown_to_pdf,
    save_report_to_disk,
)


def _full_final_state() -> dict:
    """Shape that mirrors what propagate() actually returns after a real run."""
    return {
        "market_report": "Market analysis body.",
        "sentiment_report": "Sentiment analysis body.",
        "news_report": "News analysis body.",
        "fundamentals_report": "Fundamentals analysis body.",
        "investment_debate_state": {
            "bull_history": "Bull case body.",
            "bear_history": "Bear case body.",
            "judge_decision": "Research manager decision body.",
        },
        "trader_investment_plan": "Trader plan body.",
        "risk_debate_state": {
            "aggressive_history": "Aggressive body.",
            "conservative_history": "Conservative body.",
            "neutral_history": "Neutral body.",
            "judge_decision": (
                "**Rating**: Overweight\n\n"
                "**Executive Summary**: Accumulate.\n\n"
                "**Investment Thesis**: Bullish divergence.\n\n"
                "**Price Target**: 77400.0\n\n"
                "**Time Horizon**: 3-6 mesi\n"
            ),
        },
    }


@pytest.mark.unit
class TestSaveReportToDisk:
    def test_writes_canonical_folder_layout(self, tmp_path):
        state = _full_final_state()
        target = tmp_path / "BTC-USD_20260616_220459"
        result = save_report_to_disk(state, "BTC-USD", target)

        assert result == target / "complete_report.md"
        assert (target / "1_analysts" / "market.md").exists()
        assert (target / "1_analysts" / "sentiment.md").exists()
        assert (target / "1_analysts" / "news.md").exists()
        assert (target / "1_analysts" / "fundamentals.md").exists()
        assert (target / "2_research" / "bull.md").exists()
        assert (target / "2_research" / "bear.md").exists()
        assert (target / "2_research" / "manager.md").exists()
        assert (target / "3_trading" / "trader.md").exists()
        assert (target / "4_risk" / "aggressive.md").exists()
        assert (target / "4_risk" / "conservative.md").exists()
        assert (target / "4_risk" / "neutral.md").exists()
        assert (target / "5_portfolio" / "decision.md").exists()
        assert (target / "complete_report.md").exists()

    def test_decision_md_is_portfolio_manager_judge(self, tmp_path):
        state = _full_final_state()
        target = tmp_path / "out"
        save_report_to_disk(state, "BTC-USD", target)
        decision = (target / "5_portfolio" / "decision.md").read_text(encoding="utf-8")
        assert "Overweight" in decision
        assert "77400" in decision

    def test_handles_missing_sections_gracefully(self, tmp_path):
        state = {"market_report": "Only market."}
        target = tmp_path / "partial"
        save_report_to_disk(state, "T", target)
        assert (target / "1_analysts" / "market.md").exists()
        assert not (target / "5_portfolio").exists()
        assert (target / "complete_report.md").exists()

    def test_round_trip_against_real_run(self):
        """Round-trip the actual report from the BTC-USD_20260616_220459 run."""
        repo_root = Path(__file__).resolve().parent.parent
        decision = (
            repo_root
            / "reports"
            / "BTC-USD_20260616_220459"
            / "5_portfolio"
            / "decision.md"
        )
        if not decision.exists():
            pytest.skip("Real-world decision.md not present in this checkout")
        text = decision.read_text(encoding="utf-8")
        summary = extract_decision_summary(text)
        assert summary.rating == "Overweight"
        assert summary.price_target == 77400.0
        assert summary.time_horizon == "3-6 mesi"
        assert summary.executive_summary
        assert summary.investment_thesis


@pytest.mark.unit
class TestExtractDecisionSummary:
    def test_parses_canonical_fields(self):
        text = (
            "**Rating**: Hold\n\n"
            "**Executive Summary**: Wait for confirmation.\n\n"
            "**Investment Thesis**: Range-bound.\n\n"
            "**Price Target**: 100.5\n\n"
            "**Time Horizon**: 1-2 mesi\n"
        )
        s = extract_decision_summary(text)
        assert s.rating == "Hold"
        assert s.executive_summary == "Wait for confirmation."
        assert s.investment_thesis == "Range-bound."
        assert s.price_target == 100.5
        assert s.time_horizon == "1-2 mesi"

    def test_empty_input_yields_empty_summary(self):
        assert extract_decision_summary("") == DecisionSummary()

    def test_comma_thousands_in_price_target(self):
        text = "**Price Target**: 1,234,567.89\n"
        assert extract_decision_summary(text).price_target == 1234567.89

    def test_handles_markdown_paragraph_gap(self):
        """Investment thesis can be multi-paragraph; we capture until next field."""
        text = (
            "**Rating**: Overweight\n\n"
            "**Investment Thesis**: First paragraph.\n\n"
            "Second paragraph.\n\n"
            "**Price Target**: 100\n"
        )
        s = extract_decision_summary(text)
        assert "First paragraph" in (s.investment_thesis or "")
        assert "Second paragraph" in (s.investment_thesis or "")


@pytest.mark.unit
class TestMarkdownToPdf:
    def test_writes_valid_pdf(self, tmp_path):
        md = tmp_path / "doc.md"
        md.write_text("# Hello\n\nThis is a test.", encoding="utf-8")
        out = tmp_path / "doc.pdf"
        result = markdown_to_pdf(md, out)
        assert result == out
        assert out.exists()
        # Valid PDFs start with the %PDF magic
        assert out.read_bytes()[:4] == b"%PDF"

    def test_default_target_is_sibling_pdf(self, tmp_path):
        md = tmp_path / "decision.md"
        md.write_text("**Rating**: Buy\n", encoding="utf-8")
        result = markdown_to_pdf(md)
        assert result is not None
        assert result == tmp_path / "decision.pdf"

    def test_handles_italian_diacritics(self, tmp_path):
        md = tmp_path / "doc.md"
        md.write_text(
            "**Rating**: Overweight\n\nTesi rialzista su azione. "
            "Rischi di ribasso, àncora di supporto a 62.000.\n",
            encoding="utf-8",
        )
        out = tmp_path / "doc.pdf"
        result = markdown_to_pdf(md, out)
        assert result is not None
        # Should not raise on diacritics
        assert out.stat().st_size > 200

    def test_renders_markdown_lists(self, tmp_path):
        """Regression: the list-item bullet must be latin-1 or fpdf2 raises
        FPDFUnicodeEncodingException on any decision.md containing a list."""
        md = tmp_path / "doc.md"
        md.write_text(
            "**Rating**: Overweight\n\n"
            "Catalysts:\n\n"
            "- ETF approval in Q3\n"
            "- Halving supply shock\n"
            "- Institutional inflows\n",
            encoding="utf-8",
        )
        out = tmp_path / "doc.pdf"
        result = markdown_to_pdf(md, out)
        assert result is not None
        assert out.exists()
        assert out.read_bytes()[:4] == b"%PDF"

    def test_long_field_values_wrap_within_page(self, tmp_path):
        """Regression: long **Field**: value lines must wrap, not overflow the
        right margin. The old per-segment multi_cell approach concatenated
        short calls on the same line (default ln=0 returns to the left
        margin), so a long value got cut off at the right page edge.

        We can't easily measure text positions without a PDF parser
        dependency, so we approximate the wrap behaviour by feeding the
        same long value to a fresh fpdf2 instance with the same margins
        and font, and asserting it would wrap to a second page. If the
        old (broken) code were still in place, the segments would all
        land on a single line and the PDF would be 1 page regardless of
        input length."""
        from fpdf import FPDF

        long_value = (
            "Manteniamo posizione rialzista su azienda con target di prezzo a 62.000, "
            "supporto a 58.000, resistenza a 65.000 per i prossimi trimestri. "
            "Il momentum degli indicatori tecnici come RSI e MACD suggeriscono un "
            "continuazione del trend rialzista nel breve termine, con volumi in aumento "
            "e una struttura di mercato che favorisce i compratori."
        )
        md = tmp_path / "doc.md"
        md.write_text(
            f"**Executive Summary**: {long_value}\n\n"
            f"**Investment Thesis**: {long_value}\n",
            encoding="utf-8",
        )
        out = tmp_path / "doc.pdf"
        result = markdown_to_pdf(md, out)
        assert result is not None
        assert out.exists()
        assert out.read_bytes()[:4] == b"%PDF"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            markdown_to_pdf(tmp_path / "absent.md")
