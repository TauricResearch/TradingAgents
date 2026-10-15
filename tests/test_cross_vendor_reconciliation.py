"""Unit tests for cross-vendor OHLCV reconciliation (no network).

Covers the pure parsing/note-building functions plus the tool-level gate that
decides *when* the extra vendor call is made (only when Alpha Vantage served
the primary data), so the healthy yfinance-primary path stays cost-free.
"""
import unittest
from unittest.mock import patch

from tradingagents.dataflows import reconciliation
from tradingagents.agents import tools

# Real-shape fixtures: a leading "#" header, then a header row, then rows.
# yfinance emits a pandas index date column + "Close"; Alpha Vantage emits a
# leading "timestamp" column + lowercase "close".
YF_CSV = (
    "# Stock data for RHM.DE from 2026-09-28 to 2026-10-09\n"
    "# Total records: 4\n\n"
    "Date,Open,High,Low,Close,Adj Close,Volume\n"
    "2026-09-28,1.00,1.10,0.95,1.05,1.05,100\n"
    "2026-09-29,1.05,1.15,1.00,1.10,1.10,110\n"
    "2026-09-30,1.10,1.20,1.05,1.15,1.15,120\n"
    "2026-10-01,1.15,1.25,1.10,1.20,1.20,130\n"
)
AV_MATCH_CSV = (
    "# Alpha Vantage primary for RHM.DE (queried as RHM.DE): "
    "TIME_SERIES_DAILY_ADJUSTED; close adjusted for splits and dividends.\n"
    "timestamp,open,high,low,close,adj close,volume\n"
    "2026-09-28,1.00,1.10,0.95,1.05,1.05,100\n"
    "2026-09-29,1.05,1.15,1.00,1.10,1.10,110\n"
    "2026-09-30,1.10,1.20,1.05,1.15,1.15,120\n"
    "2026-10-01,1.15,1.25,1.10,1.20,1.20,130\n"
)
AV_DIVERGE_CSV = (
    "# Alpha Vantage primary for RHM.DE (queried as RHM.DE): "
    "TIME_SERIES_DAILY_ADJUSTED; close adjusted for splits and dividends.\n"
    "timestamp,open,high,low,close,adj close,volume\n"
    "2026-09-28,1.00,1.10,0.95,1.00,1.00,100\n"
    "2026-09-29,1.05,1.15,1.00,1.00,1.00,110\n"
    "2026-09-30,1.10,1.20,1.05,1.00,1.00,120\n"
    "2026-10-01,1.15,1.25,1.10,1.00,1.00,130\n"
)


class ParseCloseSeriesTests(unittest.TestCase):
    def test_parses_yfinance_format(self):
        series = reconciliation.parse_close_series(YF_CSV)
        self.assertEqual(series["2026-10-01"], 1.20)
        self.assertEqual(len(series), 4)

    def test_parses_alpha_vantage_format(self):
        series = reconciliation.parse_close_series(AV_DIVERGE_CSV)
        self.assertEqual(series["2026-10-01"], 1.00)
        self.assertEqual(len(series), 4)

    def test_tolerates_blank_and_garbage_input(self):
        self.assertEqual(reconciliation.parse_close_series(""), {})
        self.assertEqual(reconciliation.parse_close_series("# only a header\n"), {})
        self.assertEqual(reconciliation.parse_close_series("not,csv\n###\n"), {})

    def test_never_raises_on_malformed_rows(self):
        bad = "Date,Close\n2026-10-01,abc\n2026-10-02,\n"
        self.assertEqual(reconciliation.parse_close_series(bad), {})


class BuildReconciliationNoteTests(unittest.TestCase):
    def test_matching_sources_produce_no_note(self):
        self.assertIsNone(
            reconciliation.build_reconciliation_note("RHM.DE", YF_CSV, AV_MATCH_CSV)
        )

    def test_divergent_sources_produce_note(self):
        note = reconciliation.build_reconciliation_note("RHM.DE", YF_CSV, AV_DIVERGE_CSV)
        self.assertIsNotNone(note)
        self.assertIn("RHM.DE", note)
        self.assertIn("Largest deviation", note)
        self.assertIn("CROSS-VENDOR NOTE", note)
        # The divergence is 1.20 vs 1.00 -> 16.67%
        self.assertIn("16.67%", note)

    def test_no_overlap_produces_no_note(self):
        other = (
            "# Alpha Vantage primary for X\n"
            "timestamp,close\n"
            "2026-01-01,5.0\n"
            "2026-01-02,6.0\n"
        )
        self.assertIsNone(reconciliation.build_reconciliation_note("RHM.DE", YF_CSV, other))

    def test_single_shared_day_produces_no_note(self):
        other = (
            "# Alpha Vantage primary for X\n"
            "timestamp,close\n"
            "2026-10-01,1.0\n"
            "2026-01-01,5.0\n"
        )
        # only 2026-10-01 is shared -> fewer than two shared days
        self.assertIsNone(reconciliation.build_reconciliation_note("RHM.DE", YF_CSV, other))


class ToolGateTests(unittest.TestCase):
    """The tool-level gate: only an Alpha Vantage primary triggers the note."""

    def test_disabled_flag_short_circuits(self):
        with patch("tradingagents.agents.tools.get_config",
                   return_value={"cross_vendor_reconciliation": False}):
            self.assertIsNone(
                tools._cross_vendor_note("RHM.DE", "2026-09-28", "2026-10-09", YF_CSV)
            )

    def test_yfinance_primary_is_skipped(self):
        # Even though AV diverges, a yfinance primary means nothing to verify.
        with patch("tradingagents.agents.tools.get_config",
                   return_value={"cross_vendor_reconciliation": True}):
            self.assertIsNone(
                tools._cross_vendor_note("RHM.DE", "2026-09-28", "2026-10-09", YF_CSV)
            )

    def test_av_primary_returns_note_from_other_source(self):
        with patch("tradingagents.agents.tools.get_config",
                   return_value={"cross_vendor_reconciliation": True}), \
             patch("tradingagents.agents.tools.get_vendor", return_value="yfinance,alpha_vantage"), \
             patch("tradingagents.agents.tools.VENDOR_METHODS",
                   {"get_stock_data": {"yfinance": lambda *a: YF_CSV,
                                       "alpha_vantage": lambda *a: AV_DIVERGE_CSV}}):
            note = tools._cross_vendor_note("RHM.DE", "2026-09-28", "2026-10-09",
                                            AV_DIVERGE_CSV)
            self.assertIsNotNone(note)
            self.assertIn("CROSS-VENDOR NOTE", note)

    def test_comparison_vendor_failure_is_swallowed(self):
        def boom(*a):
            raise RuntimeError("vendor down")
        with patch("tradingagents.agents.tools.get_config",
                   return_value={"cross_vendor_reconciliation": True}), \
             patch("tradingagents.agents.tools.get_vendor", return_value="yfinance,alpha_vantage"), \
             patch("tradingagents.agents.tools.VENDOR_METHODS",
                   {"get_stock_data": {"yfinance": boom,
                                       "alpha_vantage": lambda *a: AV_DIVERGE_CSV}}):
            self.assertIsNone(
                tools._cross_vendor_note("RHM.DE", "2026-09-28", "2026-10-09",
                                         AV_DIVERGE_CSV)
            )


if __name__ == "__main__":
    unittest.main()
