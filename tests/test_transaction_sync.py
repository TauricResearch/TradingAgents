import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.portfolio.transaction_sync import (
    TransactionSyncService,
    _parse_number,
    _resolve_column_indices,
    _run_gws_command,
    _transform_row,
)


@pytest.mark.unit
class RunGwsCommandTests(unittest.TestCase):
    """Tests for _run_gws_command standalone function."""

    @patch("tradingagents.portfolio.transaction_sync.subprocess.run")
    def test_parses_gws_output_with_values(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"values": [["a", "b"], ["1", "2"]]}),
            stderr="",
        )
        result = _run_gws_command("sheet123", "Sheet1!A1:Z1000")
        self.assertEqual(result, [["a", "b"], ["1", "2"]])

    @patch("tradingagents.portfolio.transaction_sync.subprocess.run")
    def test_returns_empty_list_when_values_key_missing(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"other": "data"}),
            stderr="",
        )
        result = _run_gws_command("sheet123", "range")
        self.assertEqual(result, [])

    @patch("tradingagents.portfolio.transaction_sync.subprocess.run")
    def test_returns_none_when_values_is_null(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"values": None}),
            stderr="",
        )
        result = _run_gws_command("sheet123", "range")
        self.assertIsNone(result)

    @patch("tradingagents.portfolio.transaction_sync.subprocess.run")
    def test_raises_runtime_on_missing_gws_cli(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        with self.assertRaises(RuntimeError) as ctx:
            _run_gws_command("sheet123", "range")
        self.assertIn("gws CLI not found", str(ctx.exception))

    @patch("tradingagents.portfolio.transaction_sync.subprocess.run")
    def test_raises_runtime_on_called_process_error(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "gws", stderr="error detail")
        with self.assertRaises(RuntimeError) as ctx:
            _run_gws_command("sheet123", "range")
        self.assertIn("gws CLI failed", str(ctx.exception))

    @patch("tradingagents.portfolio.transaction_sync.subprocess.run")
    def test_constructs_correct_command(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"values": []}),
            stderr="",
        )
        _run_gws_command("abc123", "Sheet1!A1:L1000")
        expected_cmd = [
            "gws",
            "sheets",
            "spreadsheets",
            "values",
            "get",
            "--params",
            json.dumps({"spreadsheetId": "abc123", "range": "Sheet1!A1:L1000"}),
        ]
        mock_run.assert_called_once_with(expected_cmd, capture_output=True, text=True, check=True)


@pytest.mark.unit
class ParseNumberTests(unittest.TestCase):
    """Tests for _parse_number standalone function."""

    def test_parses_normal_number(self):
        self.assertEqual(_parse_number("123.45"), 123.45)

    def test_returns_zero_for_empty_string(self):
        self.assertEqual(_parse_number(""), 0.0)

    def test_returns_zero_for_whitespace(self):
        self.assertEqual(_parse_number("   "), 0.0)

    def test_handles_english_commas(self):
        self.assertEqual(_parse_number("1,234.56"), 1234.56)

    def test_handles_chinese_commas(self):
        self.assertEqual(_parse_number("1，234.56"), 1234.56)

    def test_handles_negative_number(self):
        self.assertEqual(_parse_number("-50.0"), -50.0)

    def test_handles_zero(self):
        self.assertEqual(_parse_number("0"), 0.0)

    def test_strips_whitespace(self):
        self.assertEqual(_parse_number("  99.99  "), 99.99)

    def test_handles_integer_string(self):
        self.assertEqual(_parse_number("42"), 42.0)


@pytest.mark.unit
class ResolveColumnIndicesTests(unittest.TestCase):
    """Tests for _resolve_column_indices standalone function."""

    def test_resolves_all_columns(self):
        headers = ["交易时间", "代码", "名称", "成本单价", "动作", "份额变动", "手续费", "资金变动", "网格建仓"]
        indices = _resolve_column_indices(headers)
        self.assertEqual(indices["date"], 0)
        self.assertEqual(indices["ticker"], 1)
        self.assertEqual(indices["name"], 2)
        self.assertEqual(indices["price"], 3)
        self.assertEqual(indices["action"], 4)
        self.assertEqual(indices["shares"], 5)
        self.assertEqual(indices["fee"], 6)
        self.assertEqual(indices["cash_change"], 7)
        self.assertEqual(indices["tag"], 8)

    def test_omits_missing_columns(self):
        headers = ["交易时间", "代码", "名称"]
        indices = _resolve_column_indices(headers)
        self.assertIn("date", indices)
        self.assertIn("ticker", indices)
        self.assertIn("name", indices)
        self.assertNotIn("price", indices)
        self.assertNotIn("action", indices)
        self.assertNotIn("shares", indices)
        self.assertNotIn("fee", indices)
        self.assertNotIn("cash_change", indices)
        self.assertNotIn("tag", indices)

    def test_returns_empty_dict_for_empty_headers(self):
        indices = _resolve_column_indices([])
        self.assertEqual(indices, {})

    def test_returns_empty_dict_for_no_matching_headers(self):
        indices = _resolve_column_indices(["ColA", "ColB", "ColC"])
        self.assertEqual(indices, {})

    def test_handles_duplicate_headers_returns_first_index(self):
        headers = ["交易时间", "代码", "交易时间"]
        indices = _resolve_column_indices(headers)
        self.assertEqual(indices["date"], 0)


@pytest.mark.unit
class TransformRowTests(unittest.TestCase):
    """Tests for _transform_row standalone function."""

    def setUp(self):
        self.full_headers = [
            "交易时间", "代码", "名称", "成本单价", "动作", "份额变动", "手续费", "资金变动", "网格建仓"
        ]
        self.full_indices = _resolve_column_indices(self.full_headers)

    def test_transforms_full_valid_row(self):
        row = ["2024-01-15", "600519", "贵州茅台", "150.50", "买入", "100", "5.00", "-15050.00", ""]
        tx = _transform_row(row, self.full_indices)
        self.assertIsNotNone(tx)
        self.assertEqual(tx.date, "2024-01-15")
        self.assertEqual(tx.ticker, "600519")
        self.assertEqual(tx.name, "贵州茅台")
        self.assertEqual(tx.price, 150.50)
        self.assertEqual(tx.action, "买入")
        self.assertEqual(tx.shares, 100.0)
        self.assertEqual(tx.fee, 5.0)
        self.assertEqual(tx.cash_change, -15050.0)
        self.assertEqual(tx.tag, "")

    def test_returns_none_when_row_too_short(self):
        row = ["2024-01-15"]
        tx = _transform_row(row, self.full_indices)
        self.assertIsNone(tx)

    def test_returns_none_when_date_missing(self):
        row = ["", "600519", "贵州茅台", "150.50", "买入", "100", "5.00", "-15050.00", ""]
        tx = _transform_row(row, self.full_indices)
        self.assertIsNone(tx)

    def test_returns_none_when_ticker_missing(self):
        row = ["2024-01-15", "", "贵州茅台", "150.50", "买入", "100", "5.00", "-15050.00", ""]
        tx = _transform_row(row, self.full_indices)
        self.assertIsNone(tx)

    def test_returns_none_when_date_whitespace_only(self):
        row = ["   ", "600519", "贵州茅台", "150.50", "买入", "100", "5.00", "-15050.00", ""]
        tx = _transform_row(row, self.full_indices)
        self.assertIsNone(tx)

    def test_normalizes_buy_action(self):
        row = ["2024-01-15", "600519", "茅台", "150.50", "买开仓", "100", "5.00", "-15050.00", ""]
        tx = _transform_row(row, self.full_indices)
        self.assertIsNotNone(tx)
        self.assertEqual(tx.action, "买入")

    def test_normalizes_sell_action(self):
        row = ["2024-01-15", "600519", "茅台", "160.00", "卖平仓", "-100", "5.00", "16000.00", ""]
        tx = _transform_row(row, self.full_indices)
        self.assertIsNotNone(tx)
        self.assertEqual(tx.action, "卖出")

    def test_normalizes_dividend_action(self):
        row = ["2024-06-01", "600519", "茅台", "0.00", "分红到账", "0", "0", "5000.00", ""]
        tx = _transform_row(row, self.full_indices)
        self.assertIsNotNone(tx)
        self.assertEqual(tx.action, "分红")

    def test_normalizes_dividend_via_red_character(self):
        row = ["2024-06-01", "600519", "茅台", "0.00", "红利", "0", "0", "5000.00", ""]
        tx = _transform_row(row, self.full_indices)
        self.assertIsNotNone(tx)
        self.assertEqual(tx.action, "分红")

    def test_passes_through_unknown_action(self):
        row = ["2024-01-15", "600519", "茅台", "150.50", "转托管", "100", "0", "0", ""]
        tx = _transform_row(row, self.full_indices)
        self.assertIsNotNone(tx)
        self.assertEqual(tx.action, "转托管")

    def test_sets_fee_to_none_when_zero(self):
        row = ["2024-01-15", "600519", "茅台", "150.50", "买入", "100", "0", "-15050.00", ""]
        tx = _transform_row(row, self.full_indices)
        self.assertIsNotNone(tx)
        self.assertIsNone(tx.fee)

    def test_sets_cash_change_to_none_when_zero(self):
        row = ["2024-01-15", "600519", "茅台", "150.50", "分红", "0", "0", "0", ""]
        tx = _transform_row(row, self.full_indices)
        self.assertIsNotNone(tx)
        self.assertIsNone(tx.cash_change)

    def test_uses_tag_when_present(self):
        row = ["2024-01-15", "600519", "茅台", "150.50", "买入", "100", "5.00", "-15050.00", "网格建仓"]
        tx = _transform_row(row, self.full_indices)
        self.assertIsNotNone(tx)
        self.assertEqual(tx.tag, "网格建仓")

    def test_parses_number_with_commas(self):
        row = ["2024-01-15", "600519", "茅台", "1,234.56", "买入", "1,000", "12.50", "-1,234,567.00", ""]
        tx = _transform_row(row, self.full_indices)
        self.assertIsNotNone(tx)
        self.assertEqual(tx.price, 1234.56)
        self.assertEqual(tx.shares, 1000.0)
        self.assertEqual(tx.cash_change, -1234567.0)

    def test_handles_missing_optional_columns(self):
        headers = ["交易时间", "代码", "名称", "动作", "份额变动"]
        indices = _resolve_column_indices(headers)
        row = ["2024-01-15", "600519", "茅台", "买入", "100"]
        tx = _transform_row(row, indices)
        self.assertIsNotNone(tx)
        self.assertEqual(tx.price, 0.0)
        self.assertIsNone(tx.fee)
        self.assertIsNone(tx.cash_change)
        self.assertIsNone(tx.tag)
        self.assertEqual(tx.name, "茅台")


@pytest.mark.unit
class TransactionSyncServiceInitTests(unittest.TestCase):
    """Tests for TransactionSyncService.__init__."""

    def test_default_worksheet(self):
        svc = TransactionSyncService(sheet_id="test123")
        self.assertEqual(svc.sheet_id, "test123")
        self.assertEqual(svc.worksheet, "stock transitions")

    def test_custom_worksheet(self):
        svc = TransactionSyncService(sheet_id="test123", worksheet="Trades")
        self.assertEqual(svc.worksheet, "Trades")


@pytest.mark.unit
class TransactionSyncServiceSyncTests(unittest.TestCase):
    """Tests for TransactionSyncService.sync."""

    def setUp(self):
        self.svc = TransactionSyncService(sheet_id="test123")

    @patch("tradingagents.portfolio.transaction_sync._run_gws_command")
    def test_sync_returns_transactions(self, mock_run):
        mock_run.return_value = [
            ["交易时间", "代码", "名称", "成本单价", "动作", "份额变动", "手续费", "资金变动", "网格建仓"],
            ["2024-01-15", "600519", "贵州茅台", "150.50", "买入", "100", "5.00", "-15050.00", ""],
            ["2024-01-20", "002241", "歌尔股份", "28.41", "卖出", "-200", "3.00", "5682.00", ""],
        ]
        result = self.svc.sync()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].ticker, "600519")
        self.assertEqual(result[0].action, "买入")
        self.assertEqual(result[1].ticker, "002241")
        self.assertEqual(result[1].action, "卖出")

    @patch("tradingagents.portfolio.transaction_sync._run_gws_command")
    def test_sync_uses_correct_range(self, mock_run):
        mock_run.return_value = [
            ["交易时间", "代码"],
            ["2024-01-15", "600519"],
        ]
        self.svc.sync()
        mock_run.assert_called_once_with("test123", "stock transitions!A1:L1000")

    @patch("tradingagents.portfolio.transaction_sync._run_gws_command")
    def test_returns_empty_list_when_no_rows(self, mock_run):
        mock_run.return_value = []
        result = self.svc.sync()
        self.assertEqual(result, [])

    @patch("tradingagents.portfolio.transaction_sync._run_gws_command")
    def test_returns_empty_list_when_only_header(self, mock_run):
        mock_run.return_value = [
            ["交易时间", "代码", "名称", "成本单价", "动作", "份额变动", "手续费", "资金变动", "网格建仓"],
        ]
        result = self.svc.sync()
        self.assertEqual(result, [])

    @patch("tradingagents.portfolio.transaction_sync._run_gws_command")
    def test_skips_invalid_rows(self, mock_run):
        mock_run.return_value = [
            ["交易时间", "代码", "名称", "成本单价", "动作", "份额变动", "手续费", "资金变动", "网格建仓"],
            ["", "600519", "茅台", "150.50", "买入", "100", "5.00", "-15050.00", ""],
            ["2024-01-20", "", "歌尔股份", "28.41", "卖出", "-200", "3.00", "5682.00", ""],
            ["2024-01-25", "000001", "平安银行", "12.50", "买入", "500", "2.50", "-6250.00", ""],
        ]
        result = self.svc.sync()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ticker, "000001")

    @patch("tradingagents.portfolio.transaction_sync._run_gws_command")
    def test_sync_with_custom_worksheet(self, mock_run):
        mock_run.return_value = [
            ["交易时间", "代码"],
            ["2024-01-15", "600519"],
        ]
        svc = TransactionSyncService(sheet_id="test123", worksheet="Trades")
        svc.sync()
        mock_run.assert_called_once_with("test123", "Trades!A1:L1000")

    @patch("tradingagents.portfolio.transaction_sync._run_gws_command")
    def test_sync_strips_header_whitespace(self, mock_run):
        mock_run.return_value = [
            ["交易时间 ", " 代码", "名称", "成本单价", "动作", "份额变动", "手续费", "资金变动", "网格建仓"],
            ["2024-01-15", "600519", "茅台", "150.50", "买入", "100", "5.00", "-15050.00", ""],
        ]
        result = self.svc.sync()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ticker, "600519")


if __name__ == "__main__":
    unittest.main()
