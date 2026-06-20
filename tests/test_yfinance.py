import unittest
from unittest.mock import MagicMock, PropertyMock, call, patch

import pandas as pd
import pytest

from tradingagents.dataflows.symbol_utils import NoMarketDataError
from tradingagents.dataflows.y_finance import (
    _get_stock_stats_bulk,
    get_YFin_data_online,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
    get_stock_stats_indicators_window,
    get_stockstats_indicator,
)


def _make_ohlcv_df(dates):
    df = pd.DataFrame({
        "Date": pd.to_datetime(dates),
        "Open": [100.0] * len(dates),
        "High": [105.0] * len(dates),
        "Low": [99.0] * len(dates),
        "Close": [102.0] * len(dates),
        "Volume": [10000] * len(dates),
    })
    df.index = df["Date"]
    return df


def _make_financials_df():
    return pd.DataFrame(
        {"Total Revenue": [1e9], "Net Income": [2e8]},
        index=pd.Index(pd.to_datetime(["2025-12-31"]), name="endDate"),
    )


def _make_info_dict():
    return {
        "longName": "Test Corp",
        "sector": "Technology",
        "industry": "Software",
        "marketCap": 1e12,
        "trailingPE": 25.0,
        "forwardPE": 22.0,
        "pegRatio": 1.5,
        "priceToBook": 4.0,
        "trailingEps": 2.5,
        "forwardEps": 3.0,
        "dividendYield": 0.01,
        "beta": 1.2,
        "fiftyTwoWeekHigh": 150.0,
        "fiftyTwoWeekLow": 100.0,
        "fiftyDayAverage": 120.0,
        "twoHundredDayAverage": 110.0,
        "totalRevenue": 5e9,
        "grossProfits": 3e9,
        "ebitda": 1.5e9,
        "netIncomeToCommon": 1e9,
        "profitMargins": 0.2,
        "operatingMargins": 0.25,
        "returnOnEquity": 0.15,
        "returnOnAssets": 0.08,
        "debtToEquity": 0.5,
        "currentRatio": 2.0,
        "bookValue": 50.0,
        "freeCashflow": 8e8,
    }


@pytest.mark.unit
class GetYFinDataOnlineTests(unittest.TestCase):
    def setUp(self):
        self.symbol = "AAPL"
        self.start = "2025-01-01"
        self.end = "2025-01-10"
        self.canonical = "AAPL"

        dates = pd.date_range("2025-01-01", "2025-01-10", freq="B")
        self.history_df = pd.DataFrame(
            {
                "Open": [100.12, 101.34, 102.56],
                "High": [105.78, 106.89, 107.90],
                "Low": [99.01, 100.12, 101.23],
                "Close": [102.45, 103.67, 104.78],
                "Adj Close": [102.45, 103.67, 104.78],
                "Volume": [1000000, 1100000, 1200000],
            },
            index=dates[:3],
        )
        self.history_df.index = self.history_df.index.tz_localize("UTC")

    def test_returns_csv_with_header(self):
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value=self.canonical):
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = self.history_df
            with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                result = get_YFin_data_online(self.symbol, self.start, self.end)

        self.assertIn("# Stock data for AAPL from 2025-01-01 to 2025-01-10", result)
        self.assertIn("Open,High,Low,Close,Adj Close,Volume", result)
        self.assertIn("100.12", result)

    def test_numeric_columns_rounded_to_two_decimals(self):
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value=self.canonical):
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = self.history_df
            with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                result = get_YFin_data_online(self.symbol, self.start, self.end)

        for val in ["100.12", "101.34"]:
            self.assertIn(val, result)

    def test_removes_timezone_from_index(self):
        self.assertTrue(self.history_df.index.tz is not None)
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value=self.canonical):
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = self.history_df
            with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                    result = get_YFin_data_online(self.symbol, self.start, self.end)

        self.assertIn("2025-01-01", result)

    def test_empty_dataframe_raises_no_market_data_error(self):
        empty = pd.DataFrame()
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value=self.canonical):
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = empty
            with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                with self.assertRaises(NoMarketDataError):
                    get_YFin_data_online(self.symbol, self.start, self.end)

    def test_invalid_dates_return_error_string(self):
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value=self.canonical):
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = self.history_df
            with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                result = get_YFin_data_online(self.symbol, "bad-date", self.end)

        self.assertIn("Error retrieving stock data", result)

    def test_generic_exception_returns_error_string(self):
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value=self.canonical):
            mock_ticker = MagicMock()
            mock_ticker.history.side_effect = ConnectionError("network error")
            with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                result = get_YFin_data_online(self.symbol, self.start, self.end)

        self.assertIn("Error retrieving stock data for AAPL", result)
        self.assertIn("network error", result)

    def test_shows_resolved_symbol_when_different(self):
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="GC=F"):
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = self.history_df
            with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                result = get_YFin_data_online("XAUUSD+", self.start, self.end)

        self.assertIn("GC=F (from XAUUSD+)", result)


@pytest.mark.unit
class GetStockStatsIndicatorsWindowTests(unittest.TestCase):
    def test_valid_indicator_returns_data(self):
        indicator_data = {"2025-01-10": "50.5", "2025-01-09": "49.8"}
        with patch("tradingagents.dataflows.y_finance._get_stock_stats_bulk", return_value=indicator_data):
            result = get_stock_stats_indicators_window("AAPL", "close_50_sma", "2025-01-10", 2)

        self.assertIn("close_50_sma values", result)
        self.assertIn("2025-01-10: 50.5", result)
        self.assertIn("2025-01-09: 49.8", result)
        self.assertIn("50 SMA", result)

    def test_invalid_indicator_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            get_stock_stats_indicators_window("AAPL", "nonexistent_indicator", "2025-01-10", 5)
        self.assertIn("not supported", str(ctx.exception))

    def test_non_trading_day_shows_message(self):
        indicator_data = {"2025-01-10": "50.5"}
        with patch("tradingagents.dataflows.y_finance._get_stock_stats_bulk", return_value=indicator_data):
            result = get_stock_stats_indicators_window("AAPL", "close_50_sma", "2025-01-10", 3)

        self.assertIn("N/A: Not a trading day", result)

    def test_no_market_data_raised_through(self):
        with patch("tradingagents.dataflows.y_finance._get_stock_stats_bulk", side_effect=NoMarketDataError("FAKE")):
            with self.assertRaises(NoMarketDataError):
                get_stock_stats_indicators_window("FAKE", "close_50_sma", "2025-01-10", 5)

    def test_bulk_failure_falls_back_to_per_date(self):
        with patch("tradingagents.dataflows.y_finance._get_stock_stats_bulk", side_effect=Exception("bulk failed")):
            with patch("tradingagents.dataflows.y_finance.get_stockstats_indicator", return_value="52.3"):
                result = get_stock_stats_indicators_window("AAPL", "close_50_sma", "2025-01-10", 2)

        self.assertIn("2025-01-10: 52.3", result)
        self.assertIn("2025-01-09: 52.3", result)

    def test_fallback_respects_date_range(self):
        with patch("tradingagents.dataflows.y_finance._get_stock_stats_bulk", side_effect=Exception("bulk failed")):
            with patch("tradingagents.dataflows.y_finance.get_stockstats_indicator", return_value="55.0"):
                result = get_stock_stats_indicators_window("AAPL", "rsi", "2025-01-05", 3)

        self.assertIn("2025-01-05: 55.0", result)
        self.assertIn("2025-01-04: 55.0", result)
        self.assertIn("2025-01-03: 55.0", result)
        self.assertIn("2025-01-02: 55.0", result)
        self.assertEqual(result.count("55.0"), 4)

    def test_all_supported_indicators_have_descriptions(self):
        supported = [
            "close_50_sma", "close_200_sma", "close_10_ema",
            "macd", "macds", "macdh",
            "rsi", "boll", "boll_ub", "boll_lb", "atr",
            "vwma", "mfi",
        ]
        for ind in supported:
            with patch("tradingagents.dataflows.y_finance._get_stock_stats_bulk", return_value={"2025-01-10": "1.0"}):
                result = get_stock_stats_indicators_window("AAPL", ind, "2025-01-10", 1)
            self.assertNotIn("No description available", result)


@pytest.mark.unit
class GetStockStatsBulkTests(unittest.TestCase):
    @patch("tradingagents.dataflows.y_finance.load_ohlcv")
    @patch("stockstats.wrap")
    def test_returns_indicator_dict(self, mock_wrap, mock_load):
        df = _make_ohlcv_df(["2025-01-02", "2025-01-03"])
        mock_load.return_value = df
        wrapped = df.copy()
        wrapped["close_50_sma"] = [50.5, 51.2]
        mock_wrap.return_value = wrapped

        result = _get_stock_stats_bulk("AAPL", "close_50_sma", "2025-01-03")
        self.assertEqual(result, {"2025-01-02": "50.5", "2025-01-03": "51.2"})

    @patch("tradingagents.dataflows.y_finance.load_ohlcv")
    @patch("stockstats.wrap")
    def test_handles_nan_values(self, mock_wrap, mock_load):
        df = _make_ohlcv_df(["2025-01-02"])
        mock_load.return_value = df
        wrapped = df.copy()
        wrapped["rsi"] = [float("nan")]
        mock_wrap.return_value = wrapped

        result = _get_stock_stats_bulk("AAPL", "rsi", "2025-01-02")
        self.assertEqual(result["2025-01-02"], "N/A")

    @patch("tradingagents.dataflows.y_finance.load_ohlcv")
    @patch("stockstats.wrap")
    def test_handles_none_values(self, mock_wrap, mock_load):
        df = _make_ohlcv_df(["2025-01-02"])
        mock_load.return_value = df
        wrapped = df.copy()
        wrapped["atr"] = [None]
        mock_wrap.return_value = wrapped

        result = _get_stock_stats_bulk("AAPL", "atr", "2025-01-02")
        self.assertEqual(result["2025-01-02"], "N/A")


@pytest.mark.unit
class GetStockstatsIndicatorTests(unittest.TestCase):
    @patch("tradingagents.dataflows.y_finance.StockstatsUtils.get_stock_stats", return_value=55.5)
    def test_returns_str_value(self, mock_get):
        result = get_stockstats_indicator("AAPL", "close_50_sma", "2025-01-10")
        self.assertEqual(result, "55.5")
        mock_get.assert_called_once_with("AAPL", "close_50_sma", "2025-01-10")

    @patch("tradingagents.dataflows.y_finance.StockstatsUtils.get_stock_stats", side_effect=NoMarketDataError("FAKE"))
    def test_raises_no_market_data(self, mock_get):
        with self.assertRaises(NoMarketDataError):
            get_stockstats_indicator("FAKE", "close_50_sma", "2025-01-10")

    @patch("tradingagents.dataflows.y_finance.StockstatsUtils.get_stock_stats", side_effect=ValueError("bad"))
    def test_returns_empty_string_on_generic_error(self, mock_get):
        result = get_stockstats_indicator("AAPL", "rsi", "2025-01-10")
        self.assertEqual(result, "")


@pytest.mark.unit
class GetFundamentalsTests(unittest.TestCase):
    def test_returns_formatted_fundamentals(self):
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                mock_ticker = MagicMock()
                mock_ticker.info = _make_info_dict()
                with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                    result = get_fundamentals("AAPL")

        self.assertIn("Name: Test Corp", result)
        self.assertIn("Sector: Technology", result)
        self.assertIn("Market Cap: 1000000000000", result)
        self.assertIn("PE Ratio (TTM): 25.0", result)
        self.assertIn("Beta: 1.2", result)
        self.assertIn("Company Fundamentals for AAPL", result)

    def test_empty_info_raises_no_market_data(self):
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="FAKE"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                mock_ticker = MagicMock()
                mock_ticker.info = {}
                with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                    with self.assertRaises(NoMarketDataError):
                        get_fundamentals("FAKE")

    def test_no_usable_fields_raises_no_market_data(self):
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="STUB"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                mock_ticker = MagicMock()
                mock_ticker.info = {"trailingPegRatio": None}
                with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                    with self.assertRaises(NoMarketDataError):
                        get_fundamentals("STUB")

    def test_skips_none_fields(self):
        info = _make_info_dict()
        info["dividendYield"] = None
        info["beta"] = None
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                mock_ticker = MagicMock()
                mock_ticker.info = info
                with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                    result = get_fundamentals("AAPL")

        self.assertNotIn("Dividend Yield", result)
        self.assertNotIn("Beta", result)

    def test_generic_exception_returns_error_string(self):
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                mock_ticker = MagicMock()
                type(mock_ticker).info = PropertyMock(side_effect=ConnectionError("no host"))
                with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                    result = get_fundamentals("AAPL")

        self.assertIn("Error retrieving fundamentals", result)


@pytest.mark.unit
class GetBalanceSheetTests(unittest.TestCase):
    def test_quarterly_fetches_quarterly_balance_sheet(self):
        bs_df = _make_financials_df()
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                with patch("tradingagents.dataflows.y_finance.filter_financials_by_date", return_value=bs_df):
                    mock_ticker = MagicMock()
                    mock_ticker.quarterly_balance_sheet = bs_df
                    with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                        result = get_balance_sheet("AAPL", "quarterly")

        self.assertIn("Balance Sheet data for AAPL (quarterly)", result)
        self.assertIn("Total Revenue", result)

    def test_annual_fetches_annual_balance_sheet(self):
        bs_df = _make_financials_df()
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                with patch("tradingagents.dataflows.y_finance.filter_financials_by_date", return_value=bs_df):
                    mock_ticker = MagicMock()
                    mock_ticker.balance_sheet = bs_df
                    with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                        result = get_balance_sheet("AAPL", "annual")

        self.assertIn("Balance Sheet data for AAPL (annual)", result)

    def test_empty_data_raises_no_market_data(self):
        empty = pd.DataFrame()
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="FAKE"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                with patch("tradingagents.dataflows.y_finance.filter_financials_by_date", return_value=empty):
                    mock_ticker = MagicMock()
                    mock_ticker.quarterly_balance_sheet = empty
                    with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                        with self.assertRaises(NoMarketDataError):
                            get_balance_sheet("FAKE", "quarterly")

    def test_generic_exception_returns_error_string(self):
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=RuntimeError("crash")):
                mock_ticker = MagicMock()
                with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                    result = get_balance_sheet("AAPL", "quarterly")

        self.assertIn("Error retrieving balance sheet", result)

    def test_defaults_to_quarterly(self):
        bs_df = _make_financials_df()
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                with patch("tradingagents.dataflows.y_finance.filter_financials_by_date", return_value=bs_df):
                    mock_ticker = MagicMock()
                    mock_ticker.quarterly_balance_sheet = bs_df
                    with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                        result = get_balance_sheet("AAPL")

        self.assertIn("(quarterly)", result)


@pytest.mark.unit
class GetCashflowTests(unittest.TestCase):
    def test_quarterly_fetches_quarterly_cashflow(self):
        cf_df = _make_financials_df()
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                with patch("tradingagents.dataflows.y_finance.filter_financials_by_date", return_value=cf_df):
                    mock_ticker = MagicMock()
                    mock_ticker.quarterly_cashflow = cf_df
                    with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                        result = get_cashflow("AAPL", "quarterly")

        self.assertIn("Cash Flow data for AAPL (quarterly)", result)
        self.assertIn("Total Revenue", result)

    def test_annual_fetches_annual_cashflow(self):
        cf_df = _make_financials_df()
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                with patch("tradingagents.dataflows.y_finance.filter_financials_by_date", return_value=cf_df):
                    mock_ticker = MagicMock()
                    mock_ticker.cashflow = cf_df
                    with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                        result = get_cashflow("AAPL", "annual")

        self.assertIn("Cash Flow data for AAPL (annual)", result)

    def test_empty_data_raises_no_market_data(self):
        empty = pd.DataFrame()
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="FAKE"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                with patch("tradingagents.dataflows.y_finance.filter_financials_by_date", return_value=empty):
                    mock_ticker = MagicMock()
                    mock_ticker.quarterly_cashflow = empty
                    with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                        with self.assertRaises(NoMarketDataError):
                            get_cashflow("FAKE", "quarterly")

    def test_generic_exception_returns_error_string(self):
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=RuntimeError("fail")):
                mock_ticker = MagicMock()
                with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                    result = get_cashflow("AAPL")

        self.assertIn("Error retrieving cash flow", result)


@pytest.mark.unit
class GetIncomeStatementTests(unittest.TestCase):
    def test_quarterly_fetches_quarterly_income_stmt(self):
        is_df = _make_financials_df()
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                with patch("tradingagents.dataflows.y_finance.filter_financials_by_date", return_value=is_df):
                    mock_ticker = MagicMock()
                    mock_ticker.quarterly_income_stmt = is_df
                    with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                        result = get_income_statement("AAPL", "quarterly")

        self.assertIn("Income Statement data for AAPL (quarterly)", result)
        self.assertIn("Total Revenue", result)

    def test_annual_fetches_annual_income_stmt(self):
        is_df = _make_financials_df()
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                with patch("tradingagents.dataflows.y_finance.filter_financials_by_date", return_value=is_df):
                    mock_ticker = MagicMock()
                    mock_ticker.income_stmt = is_df
                    with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                        result = get_income_statement("AAPL", "annual")

        self.assertIn("Income Statement data for AAPL (annual)", result)

    def test_empty_data_raises_no_market_data(self):
        empty = pd.DataFrame()
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="FAKE"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                with patch("tradingagents.dataflows.y_finance.filter_financials_by_date", return_value=empty):
                    mock_ticker = MagicMock()
                    mock_ticker.quarterly_income_stmt = empty
                    with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                        with self.assertRaises(NoMarketDataError):
                            get_income_statement("FAKE", "quarterly")

    def test_generic_exception_returns_error_string(self):
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=RuntimeError("broken")):
                mock_ticker = MagicMock()
                with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                    result = get_income_statement("AAPL")

        self.assertIn("Error retrieving income statement", result)

    def test_defaults_to_quarterly(self):
        is_df = _make_financials_df()
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                with patch("tradingagents.dataflows.y_finance.filter_financials_by_date", return_value=is_df):
                    mock_ticker = MagicMock()
                    mock_ticker.quarterly_income_stmt = is_df
                    with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                        result = get_income_statement("AAPL")

        self.assertIn("(quarterly)", result)


@pytest.mark.unit
class GetInsiderTransactionsTests(unittest.TestCase):
    def test_returns_csv_with_header(self):
        df = pd.DataFrame(
            {"Transaction": ["Buy"], "Shares": [1000]},
            index=[0],
        )
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                mock_ticker = MagicMock()
                mock_ticker.insider_transactions = df
                with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                    result = get_insider_transactions("AAPL")

        self.assertIn("Insider Transactions data for AAPL", result)
        self.assertIn("Transaction", result)

    def test_none_data_returns_no_transactions_message(self):
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                mock_ticker = MagicMock()
                mock_ticker.insider_transactions = None
                with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                    result = get_insider_transactions("AAPL")

        self.assertEqual(result, "No insider transactions reported for symbol 'AAPL'")

    def test_empty_dataframe_returns_no_transactions_message(self):
        empty = pd.DataFrame()
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=lambda f: f()):
                mock_ticker = MagicMock()
                mock_ticker.insider_transactions = empty
                with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                    result = get_insider_transactions("AAPL")

        self.assertIn("No insider transactions reported", result)

    def test_generic_exception_returns_error_string(self):
        with patch("tradingagents.dataflows.y_finance.normalize_symbol", return_value="AAPL"):
            with patch("tradingagents.dataflows.y_finance.yf_retry", side_effect=RuntimeError("boom")):
                mock_ticker = MagicMock()
                with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
                    result = get_insider_transactions("AAPL")

        self.assertIn("Error retrieving insider transactions", result)