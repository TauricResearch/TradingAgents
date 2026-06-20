import json
import unittest
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.portfolio.sync import (
    PortfolioSyncService,
    _run_gws_command,
)


@pytest.mark.unit
class RunGwsCommandTests(unittest.TestCase):
    @patch("tradingagents.portfolio.sync.subprocess.run")
    def test_parses_gws_output(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"values": [["a", "b"], ["1", "2"]]}),
            stderr="",
        )
        result = _run_gws_command("sheet123", "Sheet1!A1:Z1000")
        self.assertEqual(result, [["a", "b"], ["1", "2"]])

    @patch("tradingagents.portfolio.sync.subprocess.run")
    def test_raises_runtime_on_missing_gws(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        with self.assertRaises(RuntimeError):
            _run_gws_command("sheet123", "range")

    @patch("tradingagents.portfolio.sync.subprocess.run")
    def test_raises_runtime_on_called_process_error(self, mock_run):
        mock_run.side_effect = __import__("subprocess").CalledProcessError(1, "gws")
        with self.assertRaises(RuntimeError):
            _run_gws_command("sheet123", "range")


@pytest.mark.unit
class PortfolioSyncInitTests(unittest.TestCase):
    def test_default_worksheet(self):
        svc = PortfolioSyncService(sheet_id="test123")
        self.assertEqual(svc.sheet_id, "test123")
        self.assertEqual(svc.worksheet, "total")

    def test_custom_worksheet(self):
        svc = PortfolioSyncService(sheet_id="test123", worksheet="custom")
        self.assertEqual(svc.worksheet, "custom")


@pytest.mark.unit
class PortfolioSyncTransformRowsTests(unittest.TestCase):
    def setUp(self):
        self.svc = PortfolioSyncService(sheet_id="test")

    def test_returns_empty_for_no_rows(self):
        result = self.svc._transform_rows([])
        self.assertEqual(result, [])

    def test_returns_empty_for_header_only(self):
        result = self.svc._transform_rows([["代码", "资产名称"]])
        self.assertEqual(result, [])

    def test_transforms_valid_row(self):
        rows = [
            ["代码", "资产名称", "持仓成本", "持仓数量", "现价", "投入本金 (元)", "盈亏率", "仓位占比", "网格策略"],
            ["600519", "贵州茅台", "1500.00", "100", "1600.00", "150000.00", "6.67%", "50.00%", ""],
        ]
        result = self.svc._transform_rows(rows)
        self.assertEqual(len(result), 1)
        h = result[0]
        self.assertEqual(h.ticker, "600519.SS")
        self.assertEqual(h.shares, 100.0)
        self.assertEqual(h.avg_cost, 1500.0)

    def test_skips_rows_with_missing_required_columns(self):
        rows = [
            ["代码", "资产名称", "持仓成本", "持仓数量"],
            ["600519", "贵州茅台", "1500.00", ""],
        ]
        result = self.svc._transform_rows(rows)
        self.assertEqual(len(result), 0)

    def test_skips_rows_with_header_row_ticker(self):
        rows = [
            ["代码", "资产名称", "持仓成本", "持仓数量", "现价"],
            ["合计", "", "", "", ""],
        ]
        result = self.svc._transform_rows(rows)
        self.assertEqual(len(result), 0)


@pytest.mark.unit
class PortfolioSyncSingleRowTests(unittest.TestCase):
    def setUp(self):
        self.svc = PortfolioSyncService(sheet_id="test")
        self.headers = ["代码", "资产名称", "持仓成本", "持仓数量", "现价", "投入本金 (元)", "盈亏率", "仓位占比", "网格策略"]
        self.indices = self.svc._resolve_column_indices(self.headers)

    def test_invalid_ticker_returns_none(self):
        row = ["-", "", "", "", "", "", "", "", ""]
        result = self.svc._transform_single_row(row, self.indices)
        self.assertIsNone(result)

    def test_row_too_short_returns_none(self):
        row = ["600519"]
        result = self.svc._transform_single_row(row, self.indices)
        self.assertIsNone(result)

    def test_parses_pnl_as_percentage(self):
        row = ["600519", "茅台", "1500", "100", "1600", "150000", "-10.70%", "50%", ""]
        result = self.svc._transform_single_row(row, self.indices)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.pnl_pct, -0.107)
        self.assertAlmostEqual(result.weight, 0.5)

    def test_handles_missing_optional_pnl(self):
        headers = ["代码", "资产名称", "持仓成本", "持仓数量"]
        indices = self.svc._resolve_column_indices(headers)
        row = ["600519", "茅台", "1500", "100"]
        result = self.svc._transform_single_row(row, indices)
        self.assertIsNotNone(result)
        self.assertIsNone(result.pnl_pct)

    def test_handles_invalid_market_price_gracefully(self):
        headers = ["代码", "资产名称", "持仓成本", "持仓数量", "现价"]
        indices = self.svc._resolve_column_indices(headers)
        row = ["600519", "茅台", "1500", "100", "N/A"]
        result = self.svc._transform_single_row(row, indices)
        self.assertIsNotNone(result)
        self.assertIsNone(result.market_price)


@pytest.mark.unit
class PortfolioSyncIntegration(unittest.TestCase):
    @patch.object(PortfolioSyncService, "_fetch_from_gsheet")
    def test_sync_full_flow(self, mock_fetch):
        mock_fetch.return_value = [
            ["代码", "资产名称", "持仓成本", "持仓数量", "现价", "投入本金 (元)", "盈亏率", "仓位占比", "网格策略"],
            ["600519", "贵州茅台", "1500.00", "100", "1600.00", "150000.00", "6.67%", "50.00%", ""],
            ["002241", "歌尔股份", "28.41", "4500", "25.37", "127845.00", "-10.70%", "9.59%", "网格宽度: +3%/-3%"],
        ]
        svc = PortfolioSyncService(sheet_id="test123")
        portfolio = svc.sync()
        self.assertEqual(len(portfolio.holdings), 2)
        self.assertEqual(portfolio.summary["total_holdings"], 2)
        self.assertIsNotNone(portfolio.metadata.updated_at)
        self.assertEqual(portfolio.metadata.source_type, "google_sheet")


# =========================================================================
# Edge-case tests merged from test_remaining_coverage.py
# =========================================================================


@pytest.mark.unit
class PortfolioSyncEdgeCases(unittest.TestCase):
    """Lines 121-122, 153, 197-198, 205-206, 215-216, 224-225."""

    def setUp(self):
        self.svc = PortfolioSyncService(sheet_id="test123")

    @patch("tradingagents.portfolio.sync._run_gws_command")
    def test_fetch_from_gsheet_delegates(self, mock_run):
        """Lines 121-122: _fetch_from_gsheet builds range and calls _run_gws_command."""
        mock_run.return_value = [["a"]]
        result = self.svc._fetch_from_gsheet()
        mock_run.assert_called_once_with("test123", "total!A1:Z1000")
        self.assertEqual(result, [["a"]])

    def test_required_column_missing_raises(self):
        """Line 153: required column not found in headers."""
        headers = ["资产名称", "持仓数量", "现价"]
        with self.assertRaises(ValueError) as ctx:
            self.svc._resolve_column_indices(headers)
        self.assertIn("Required column", str(ctx.exception))

    def _make_indices(self, fields):
        headers = [self.svc.column_map[f] for f in fields]
        return self.svc._resolve_column_indices(headers)

    def test_parse_failure_market_price_skipped(self):
        """Lines 197-198: invalid market_price silently skipped."""
        indices = self._make_indices(["ticker", "name", "avg_cost", "shares", "market_price"])
        row = ["600519", "茅台", "1500", "100", "not-a-number"]
        result = self.svc._transform_single_row(row, indices)
        self.assertIsNotNone(result)
        self.assertIsNone(result.market_price)

    def test_parse_failure_invested_amount_skipped(self):
        """Lines 205-206: invalid invested_amount silently skipped."""
        indices = self._make_indices(["ticker", "name", "avg_cost", "shares", "invested_amount"])
        row = ["600519", "茅台", "1500", "100", "bad-value"]
        result = self.svc._transform_single_row(row, indices)
        self.assertIsNotNone(result)
        self.assertIsNone(result.invested_amount)

    def test_parse_failure_pnl_pct_skipped(self):
        """Lines 215-216: invalid pnl_pct silently skipped."""
        indices = self._make_indices(["ticker", "name", "avg_cost", "shares", "pnl_pct"])
        row = ["600519", "茅台", "1500", "100", "not-a-pct"]
        result = self.svc._transform_single_row(row, indices)
        self.assertIsNotNone(result)
        self.assertIsNone(result.pnl_pct)

    def test_parse_failure_weight_skipped(self):
        """Lines 224-225: invalid weight silently skipped."""
        indices = self._make_indices(["ticker", "name", "avg_cost", "shares", "weight"])
        row = ["600519", "茅台", "1500", "100", "bad-weight"]
        result = self.svc._transform_single_row(row, indices)
        self.assertIsNotNone(result)
        self.assertIsNone(result.weight)


if __name__ == "__main__":
    unittest.main()