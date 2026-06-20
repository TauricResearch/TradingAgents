from __future__ import annotations

import json
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

import pytest

from cli.utils import normalize_ticker_symbol
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.ticker_resolver import (
    _append_a_share_suffix,
    _build_name_map,
    _fetch_company_name,
    _fetch_company_name_from_db,
    _is_numeric_code,
    _load_name_cache,
    _resolve_chinese_name,
    resolve_ticker,
)


def _reset_cache():
    import tradingagents.ticker_resolver as tr
    tr._CACHE = None


@pytest.mark.unit
class IsNumericCodeTests(unittest.TestCase):
    def test_numeric_string(self):
        self.assertTrue(_is_numeric_code("600519"))

    def test_non_numeric_string(self):
        self.assertFalse(_is_numeric_code("AAPL"))

    def test_mixed_string(self):
        self.assertFalse(_is_numeric_code("600ABC"))

    def test_empty_string(self):
        self.assertFalse(_is_numeric_code(""))


@pytest.mark.unit
class AppendAShareSuffixTests(unittest.TestCase):
    def test_shanghai_6_prefix(self):
        self.assertEqual(_append_a_share_suffix("600519"), "600519.SS")

    def test_shanghai_688_prefix(self):
        self.assertEqual(_append_a_share_suffix("688001"), "688001.SS")

    def test_shenzhen_0_prefix(self):
        self.assertEqual(_append_a_share_suffix("000001"), "000001.SZ")

    def test_shenzhen_002_prefix(self):
        self.assertEqual(_append_a_share_suffix("002241"), "002241.SZ")

    def test_shenzhen_300_prefix(self):
        self.assertEqual(_append_a_share_suffix("300750"), "300750.SZ")

    def test_beijing_83_prefix(self):
        self.assertEqual(_append_a_share_suffix("830123"), "830123.BJ")

    def test_raises_on_unknown_prefix(self):
        with self.assertRaises(ValueError):
            _append_a_share_suffix("500000")

    def test_raises_on_short_code(self):
        with self.assertRaises(ValueError):
            _append_a_share_suffix("123")


@pytest.mark.unit
class LoadNameCacheTests(unittest.TestCase):
    def setUp(self):
        _reset_cache()

    def tearDown(self):
        _reset_cache()

    @patch("tradingagents.ticker_resolver.os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=MagicMock)
    def test_load_from_file(self, mock_open, mock_exists):
        fh = MagicMock()
        fh.__enter__.return_value = fh
        fh.read.return_value = json.dumps({"贵州茅台": "600519"})
        mock_open.return_value = fh

        cache = _load_name_cache()
        self.assertEqual(cache, {"贵州茅台": "600519"})

    @patch("tradingagents.ticker_resolver.os.path.exists", return_value=False)
    def test_file_missing_returns_empty_dict(self, mock_exists):
        cache = _load_name_cache()
        self.assertEqual(cache, {})

    @patch("tradingagents.ticker_resolver.os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=MagicMock)
    def test_cache_already_loaded(self, mock_open, mock_exists):
        import tradingagents.ticker_resolver as tr
        tr._CACHE = {"already": "loaded"}
        cache = _load_name_cache()
        self.assertEqual(cache, {"already": "loaded"})
        mock_open.assert_not_called()


@pytest.mark.unit
class BuildNameMapTests(unittest.TestCase):
    def setUp(self):
        _reset_cache()

    def tearDown(self):
        _reset_cache()

    @patch("akshare.stock_info_a_code_name")
    def test_build_name_map_success(self, mock_stock_info):
        import pandas as pd
        df = pd.DataFrame({
            "code": ["600519", "000001", "002241"],
            "name": ["贵州茅台", "平安银行", "歌尔股份"],
        })
        mock_stock_info.return_value = df

        result = _build_name_map()
        self.assertEqual(result, {
            "贵州茅台": "600519",
            "平安银行": "000001",
            "歌尔股份": "002241",
        })

    def test_build_name_map_import_error(self):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "akshare":
                raise ImportError("No module named akshare")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with self.assertRaises(ImportError) as ctx:
                _build_name_map()
            self.assertIn("akshare", str(ctx.exception))


@pytest.mark.unit
class ResolveChineseNamePartialMatchTests(unittest.TestCase):
    def setUp(self):
        _reset_cache()

    def tearDown(self):
        _reset_cache()

    @patch("tradingagents.ticker_resolver._load_name_cache")
    def test_partial_match_input_in_full_name(self, mock_load):
        mock_load.return_value = {"山东黄金矿业": "600547"}
        result = _resolve_chinese_name("黄金")
        self.assertEqual(result, "600547")

    @patch("tradingagents.ticker_resolver._load_name_cache")
    def test_reverse_partial_match_full_name_in_input(self, mock_load):
        mock_load.return_value = {"黄金": "600547"}
        result = _resolve_chinese_name("山东黄金")
        self.assertEqual(result, "600547")

    @patch("tradingagents.ticker_resolver._load_name_cache")
    def test_fuzzy_match_success(self, mock_load):
        mock_load.return_value = {"贵州茅台": "600519"}
        result = _resolve_chinese_name("贵州矛台")
        self.assertEqual(result, "600519")

    @patch("tradingagents.ticker_resolver._load_name_cache")
    @patch("tradingagents.ticker_resolver._build_name_map")
    def test_fuzzy_match_no_result_raises(self, mock_build, mock_load):
        mock_load.return_value = {}
        mock_build.return_value = {}
        with self.assertRaises(ValueError) as ctx:
            _resolve_chinese_name("完全不存在的股票")
        self.assertIn("未找到", str(ctx.exception))

    @patch("tradingagents.ticker_resolver._load_name_cache")
    @patch("tradingagents.ticker_resolver._build_name_map")
    def test_raise_includes_suggestions_when_available(self, mock_build, mock_load):
        mock_load.return_value = {}
        mock_build.return_value = {"贵州茅台": "600519", "贵州燃气": "600903"}
        with self.assertRaises(ValueError) as ctx:
            _resolve_chinese_name("贵州匹")
        msg = str(ctx.exception)
        self.assertIn("您是否想输入", msg)
        self.assertIn("贵州", msg)


@pytest.mark.unit
class CacheMissRebuildTests(unittest.TestCase):
    def setUp(self):
        _reset_cache()

    def tearDown(self):
        _reset_cache()

    @patch("tradingagents.ticker_resolver._load_name_cache")
    @patch("tradingagents.ticker_resolver._build_name_map")
    @patch("tradingagents.ticker_resolver._save_name_cache")
    def test_cache_miss_rebuild_success(self, mock_save, mock_build, mock_load):
        mock_load.side_effect = [{}, {"歌尔股份": "002241"}]
        mock_build.return_value = {"歌尔股份": "002241"}
        result = _resolve_chinese_name("歌尔股份")
        self.assertEqual(result, "002241")
        mock_build.assert_called_once()
        mock_save.assert_called_once_with({"歌尔股份": "002241"})


@pytest.mark.unit
class FetchCompanyNameFromDBTests(unittest.TestCase):
    @patch("tradingagents.ticker_resolver.os.path.exists", return_value=False)
    def test_db_not_found_returns_none(self, mock_exists):
        result = _fetch_company_name_from_db("600519.SS")
        self.assertIsNone(result)

    @patch("tradingagents.ticker_resolver.os.path.exists", return_value=True)
    @patch("sqlite3.connect")
    def test_db_returns_name(self, mock_connect, mock_exists):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = ("贵州茅台",)
        mock_connect.return_value = mock_conn

        result = _fetch_company_name_from_db("600519.SS")
        self.assertEqual(result, "贵州茅台")

    @patch("tradingagents.ticker_resolver.os.path.exists", return_value=True)
    @patch("sqlite3.connect")
    def test_db_fetchone_returns_none(self, mock_connect, mock_exists):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_connect.return_value = mock_conn

        result = _fetch_company_name_from_db("UNKNOWN.SS")
        self.assertIsNone(result)

    @patch("tradingagents.ticker_resolver.os.path.exists", return_value=True)
    @patch("sqlite3.connect")
    def test_db_exception_returns_none(self, mock_connect, mock_exists):
        mock_connect.side_effect = sqlite3.OperationalError("database locked")
        result = _fetch_company_name_from_db("600519.SS")
        self.assertIsNone(result)


@pytest.mark.unit
class FetchCompanyNameTests(unittest.TestCase):
    @patch("yfinance.Ticker")
    def test_yfinance_returns_longName(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {"longName": "Apple Inc.", "shortName": "Apple"}
        mock_ticker_cls.return_value = mock_ticker
        result = _fetch_company_name("AAPL")
        self.assertEqual(result, "Apple Inc.")

    @patch("yfinance.Ticker")
    def test_yfinance_falls_back_to_shortName(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {"shortName": "Apple"}
        mock_ticker_cls.return_value = mock_ticker
        result = _fetch_company_name("AAPL")
        self.assertEqual(result, "Apple")

    @patch("yfinance.Ticker")
    def test_yfinance_exception_returns_none(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = Exception("API error")
        result = _fetch_company_name("BROKEN")
        self.assertIsNone(result)

    @patch("yfinance.Ticker")
    def test_yfinance_empty_info_returns_none(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker_cls.return_value = mock_ticker
        result = _fetch_company_name("UNKNOWN")
        self.assertIsNone(result)


@pytest.mark.unit
class ResolveTickerTests(unittest.TestCase):
    def test_empty_input_raises(self):
        with self.assertRaises(ValueError):
            resolve_ticker("")

    def test_whitespace_input_raises(self):
        with self.assertRaises(ValueError):
            resolve_ticker("   ")

    @patch("tradingagents.ticker_resolver._fetch_company_name_from_db", return_value="贵州茅台")
    @patch("tradingagents.ticker_resolver._fetch_company_name", return_value=None)
    def test_numeric_a_share(
        self, mock_fetch, mock_db
    ):
        result = resolve_ticker("600519")
        self.assertEqual(result["ticker"], "600519.SS")
        self.assertEqual(result["company_name"], "贵州茅台")

    @patch("tradingagents.ticker_resolver._fetch_company_name_from_db", return_value=None)
    @patch("tradingagents.ticker_resolver._fetch_company_name")
    def test_suffix_match_extracts_ticker(
        self, mock_fetch_name, mock_db
    ):
        mock_fetch_name.return_value = "Apple Inc."
        result = resolve_ticker("AAPL.SS")
        self.assertEqual(result["ticker"], "AAPL.SS")
        self.assertEqual(result["company_name"], "Apple Inc.")

    @patch("tradingagents.ticker_resolver._fetch_company_name_from_db", return_value=None)
    @patch("tradingagents.ticker_resolver._fetch_company_name", return_value=None)
    def test_suffix_match_returns_empty_name_when_unavailable(
        self, mock_fetch, mock_db
    ):
        result = resolve_ticker("UNKNOWN.TO")
        self.assertEqual(result["ticker"], "UNKNOWN.TO")
        self.assertEqual(result["company_name"], "")

    @patch("tradingagents.ticker_resolver._fetch_company_name_from_db", return_value=None)
    @patch("tradingagents.ticker_resolver._fetch_company_name")
    def test_international_ticker(self, mock_fetch_name, mock_db):
        mock_fetch_name.return_value = "Tesla Inc."
        result = resolve_ticker("tsla")
        self.assertEqual(result["ticker"], "TSLA")
        self.assertEqual(result["company_name"], "Tesla Inc.")

    @patch("tradingagents.ticker_resolver._fetch_company_name_from_db", return_value=None)
    @patch("tradingagents.ticker_resolver._fetch_company_name", return_value=None)
    def test_international_ticker_returns_empty_name(self, mock_fetch, mock_db):
        result = resolve_ticker("UNKNOWN")
        self.assertEqual(result["ticker"], "UNKNOWN")
        self.assertEqual(result["company_name"], "")

    @patch("tradingagents.ticker_resolver._load_name_cache", return_value={"歌尔股份": "002241"})
    @patch("tradingagents.ticker_resolver._fetch_company_name_from_db", return_value="歌尔股份")
    @patch("tradingagents.ticker_resolver._fetch_company_name", return_value=None)
    def test_chinese_name_resolution(
        self, mock_fetch, mock_db, mock_cache
    ):
        result = resolve_ticker("歌尔股份")
        self.assertEqual(result["ticker"], "002241.SZ")
        self.assertEqual(result["company_name"], "歌尔股份")

    @patch("tradingagents.ticker_resolver._load_name_cache", return_value={})
    @patch("tradingagents.ticker_resolver._build_name_map")
    @patch("tradingagents.ticker_resolver._fetch_company_name_from_db", return_value=None)
    @patch("tradingagents.ticker_resolver._fetch_company_name", return_value=None)
    def test_chinese_name_cache_miss_raises(
        self, mock_fetch, mock_db, mock_build, mock_cache
    ):
        mock_build.return_value = {}
        with self.assertRaises(ValueError):
            resolve_ticker("不存在的公司")


@pytest.mark.unit
class InternationalTickerTests(unittest.TestCase):
    @patch("tradingagents.ticker_resolver._fetch_company_name_from_db", return_value=None)
    @patch("tradingagents.ticker_resolver._fetch_company_name")
    def test_international_ticker_with_name(self, mock_fetch_name, mock_db):
        mock_fetch_name.return_value = "Tesla Inc."
        result = resolve_ticker("TSLA")
        self.assertEqual(result["ticker"], "TSLA")
        self.assertEqual(result["company_name"], "Tesla Inc.")

    @patch("tradingagents.ticker_resolver._fetch_company_name_from_db", return_value=None)
    @patch("tradingagents.ticker_resolver._fetch_company_name", return_value=None)
    def test_international_ticker_empty_name(self, mock_fetch_name, mock_db):
        result = resolve_ticker("UNKNOWN")
        self.assertEqual(result["ticker"], "UNKNOWN")
        self.assertEqual(result["company_name"], "")


@pytest.mark.unit
class ResolveTickerChineseIntegrationTests(unittest.TestCase):
    def setUp(self):
        _reset_cache()

    def tearDown(self):
        _reset_cache()

    @patch("tradingagents.ticker_resolver._load_name_cache", return_value={"歌尔股份": "002241"})
    @patch("tradingagents.ticker_resolver._fetch_company_name_from_db", return_value=None)
    @patch("tradingagents.ticker_resolver._fetch_company_name")
    def test_chinese_name_falls_back_to_yfinance(
        self, mock_fetch, mock_db, mock_cache
    ):
        mock_fetch.return_value = "Goertek Inc."
        result = resolve_ticker("歌尔股份")
        self.assertEqual(result["ticker"], "002241.SZ")
        self.assertEqual(result["company_name"], "Goertek Inc.")

    @patch("tradingagents.ticker_resolver._load_name_cache", return_value={"歌尔股份": "002241"})
    @patch("tradingagents.ticker_resolver._fetch_company_name_from_db", return_value="歌尔股份")
    @patch("tradingagents.ticker_resolver._fetch_company_name", return_value=None)
    def test_chinese_name_uses_db_first(
        self, mock_fetch, mock_db, mock_cache
    ):
        result = resolve_ticker("歌尔股份")
        self.assertEqual(result["company_name"], "歌尔股份")

    @patch("tradingagents.ticker_resolver._load_name_cache", return_value={"宝钢股份": "600019"})
    @patch("tradingagents.ticker_resolver._fetch_company_name_from_db", return_value=None)
    @patch("tradingagents.ticker_resolver._fetch_company_name", return_value=None)
    def test_chinese_name_no_name_found(
        self, mock_fetch, mock_db, mock_cache
    ):
        result = resolve_ticker("宝钢股份")
        self.assertEqual(result["ticker"], "600019.SS")
        self.assertEqual(result["company_name"], "")


@pytest.mark.unit
class TickerSymbolHandlingTests(unittest.TestCase):
    def test_normalize_ticker_symbol_preserves_exchange_suffix(self):
        self.assertEqual(normalize_ticker_symbol(" cnc.to "), "CNC.TO")

    def test_build_instrument_context_mentions_exact_symbol(self):
        context = build_instrument_context("7203.T")
        self.assertIn("7203.T", context)
        self.assertIn("exchange suffix", context)

    def test_single_get_ticker_no_shadow(self):
        import cli.main
        import cli.utils
        self.assertIs(cli.main.get_ticker, cli.utils.get_ticker)


if __name__ == "__main__":
    unittest.main()
