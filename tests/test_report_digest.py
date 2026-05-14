"""Regression tests for the analyst-report digest used by debaters."""

import unittest

import pytest

from tradingagents.agents.utils.agent_utils import (
    build_reports_block,
    summarize_report,
)


@pytest.mark.unit
class SummarizeReportTests(unittest.TestCase):
    def test_short_report_passes_through_unchanged(self):
        report = "Quick take: AAPL trending up.\n\n| key | value |\n|---|---|\n| RSI | 62 |"
        self.assertEqual(summarize_report(report, max_chars=500), report)

    def test_empty_report_returns_empty_string(self):
        self.assertEqual(summarize_report("", max_chars=500), "")
        self.assertEqual(summarize_report(None, max_chars=500), "")  # type: ignore[arg-type]

    def test_long_report_preserves_head_and_tail_table(self):
        head = "INTRODUCTION: " + ("body sentence. " * 200)
        tail_table = (
            "| Metric | Value |\n"
            "|---|---|\n"
            "| RSI | 62 |\n"
            "| MACD | bullish |\n"
        )
        report = head + tail_table
        digest = summarize_report(report, max_chars=800)
        self.assertLess(len(digest), len(report))
        self.assertIn("INTRODUCTION", digest)
        # The closing markdown table is the highest-signal tail content.
        self.assertIn("| MACD | bullish |", digest)
        self.assertIn("truncated", digest)


@pytest.mark.unit
class BuildReportsBlockTests(unittest.TestCase):
    def test_renders_all_four_report_sections_when_present(self):
        state = {
            "market_report": "MR-body",
            "sentiment_report": "SR-body",
            "news_report": "NR-body",
            "fundamentals_report": "FR-body",
        }
        block = build_reports_block(state, max_chars_per_report=500)
        self.assertIn("### Market report", block)
        self.assertIn("### Sentiment report", block)
        self.assertIn("### News report", block)
        self.assertIn("### Fundamentals report", block)
        self.assertIn("MR-body", block)
        self.assertIn("FR-body", block)

    def test_skips_missing_or_empty_reports(self):
        state = {
            "market_report": "MR-only",
            "sentiment_report": "",
            # news_report intentionally absent
            "fundamentals_report": "   ",
        }
        block = build_reports_block(state)
        self.assertIn("### Market report", block)
        self.assertNotIn("### Sentiment report", block)
        self.assertNotIn("### News report", block)
        # Whitespace-only reports are skipped via summarize_report's strip()
        self.assertNotIn("### Fundamentals report", block)

    def test_long_report_is_compressed_inside_block(self):
        long_body = "X" * 6000
        state = {
            "market_report": long_body,
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
        }
        block = build_reports_block(state, max_chars_per_report=1000)
        self.assertLess(len(block), 1500)
        self.assertIn("truncated", block)


if __name__ == "__main__":
    unittest.main()
