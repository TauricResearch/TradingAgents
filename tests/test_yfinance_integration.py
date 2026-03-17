"""Integration tests for the yfinance data layer.

All external network calls are mocked so these tests run offline and without
rate-limit concerns.  The mocks reproduce realistic yfinance return shapes so
that the code-under-test (y_finance.py) exercises every branch that matters.
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, PropertyMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv_df(start="2024-01-02", periods=5):
    """Return a minimal OHLCV DataFrame with a timezone-aware DatetimeIndex."""
    idx = pd.date_range(start, periods=periods, freq="B", tz="America/New_York")
    return pd.DataFrame(
        {
            "Open":   [150.0, 151.0, 152.0, 153.0, 154.0][:periods],
            "High":   [155.0, 156.0, 157.0, 158.0, 159.0][:periods],
            "Low":    [148.0, 149.0, 150.0, 151.0, 152.0][:periods],
            "Close":  [152.0, 153.0, 154.0, 155.0, 156.0][:periods],
            "Volume": [1_000_000] * periods,
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# get_YFin_data_online
# ---------------------------------------------------------------------------

class TestGetYFinDataOnline:
    """Tests for get_YFin_data_online."""

    def test_returns_csv_string_on_success(self):
        """Valid symbol and date range returns a CSV-formatted string with header."""
        from tradingagents.dataflows.y_finance import get_YFin_data_online

        df = _make_ohlcv_df()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_YFin_data_online("AAPL", "2024-01-02", "2024-01-08")

        assert isinstance(result, str)
        assert "# Stock data for AAPL" in result
        assert "# Total records:" in result
        assert "Close" in result  # CSV column header

    def test_symbol_is_uppercased(self):
        """Symbol is normalised to upper-case regardless of how it is supplied."""
        from tradingagents.dataflows.y_finance import get_YFin_data_online

        df = _make_ohlcv_df()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker) as mock_cls:
            get_YFin_data_online("aapl", "2024-01-02", "2024-01-08")
            mock_cls.assert_called_once_with("AAPL")

    def test_empty_dataframe_returns_no_data_message(self):
        """When yfinance returns an empty DataFrame a clear message is returned."""
        from tradingagents.dataflows.y_finance import get_YFin_data_online

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_YFin_data_online("INVALID", "2024-01-02", "2024-01-08")

        assert "No data found" in result
        assert "INVALID" in result

    def test_invalid_date_format_raises_value_error(self):
        """Malformed date strings raise ValueError before any network call is made."""
        from tradingagents.dataflows.y_finance import get_YFin_data_online

        with pytest.raises(ValueError):
            get_YFin_data_online("AAPL", "2024/01/02", "2024-01-08")

    def test_timezone_stripped_from_index(self):
        """Timezone info is removed from the index for cleaner output."""
        from tradingagents.dataflows.y_finance import get_YFin_data_online

        df = _make_ohlcv_df()
        assert df.index.tz is not None  # pre-condition

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_YFin_data_online("AAPL", "2024-01-02", "2024-01-08")

        # Timezone strings like "+00:00" or "UTC" should not appear in the CSV portion
        csv_lines = result.split("\n")
        data_lines = [l for l in csv_lines if l and not l.startswith("#")]
        for line in data_lines:
            assert "+00:00" not in line
            assert "UTC" not in line

    def test_numeric_columns_are_rounded(self):
        """OHLC values in the returned CSV are rounded to 2 decimal places."""
        from tradingagents.dataflows.y_finance import get_YFin_data_online

        idx = pd.date_range("2024-01-02", periods=1, freq="B", tz="UTC")
        df = pd.DataFrame(
            {"Open": [150.123456], "High": [155.987654], "Low": [148.0], "Close": [152.999999], "Volume": [1_000_000]},
            index=idx,
        )
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_YFin_data_online("AAPL", "2024-01-02", "2024-01-02")

        assert "150.12" in result
        assert "155.99" in result

    def test_network_timeout_propagates(self):
        """A TimeoutError from yfinance propagates to the caller."""
        from tradingagents.dataflows.y_finance import get_YFin_data_online

        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = TimeoutError("request timed out")

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            with pytest.raises(TimeoutError):
                get_YFin_data_online("AAPL", "2024-01-02", "2024-01-08")


# ---------------------------------------------------------------------------
# get_fundamentals
# ---------------------------------------------------------------------------

class TestGetFundamentals:
    """Tests for the yfinance get_fundamentals function."""

    def test_returns_fundamentals_string_on_success(self):
        """When info is populated, fundamentals are returned as a formatted string."""
        from tradingagents.dataflows.y_finance import get_fundamentals

        mock_info = {
            "longName": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "marketCap": 3_000_000_000_000,
            "trailingPE": 30.5,
            "beta": 1.2,
            "fiftyTwoWeekHigh": 200.0,
            "fiftyTwoWeekLow": 150.0,
        }
        mock_ticker = MagicMock()
        type(mock_ticker).info = PropertyMock(return_value=mock_info)

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_fundamentals("AAPL")

        assert "# Company Fundamentals for AAPL" in result
        assert "Apple Inc." in result
        assert "Technology" in result

    def test_empty_info_returns_no_data_message(self):
        """Empty info dict returns a clear 'no data' message."""
        from tradingagents.dataflows.y_finance import get_fundamentals

        mock_ticker = MagicMock()
        type(mock_ticker).info = PropertyMock(return_value={})

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_fundamentals("AAPL")

        assert "No fundamentals data" in result

    def test_exception_returns_error_string(self):
        """An exception from yfinance yields a safe error string (not a raise)."""
        from tradingagents.dataflows.y_finance import get_fundamentals

        mock_ticker = MagicMock()
        type(mock_ticker).info = PropertyMock(side_effect=ConnectionError("network error"))

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_fundamentals("AAPL")

        assert "Error" in result
        assert "AAPL" in result


# ---------------------------------------------------------------------------
# get_balance_sheet
# ---------------------------------------------------------------------------

class TestGetBalanceSheet:
    """Tests for yfinance get_balance_sheet."""

    def _mock_balance_df(self):
        return pd.DataFrame(
            {"2023-12-31": [1_000_000], "2022-12-31": [900_000]},
            index=["Total Assets"],
        )

    def test_quarterly_balance_sheet_success(self):
        from tradingagents.dataflows.y_finance import get_balance_sheet

        mock_ticker = MagicMock()
        mock_ticker.quarterly_balance_sheet = self._mock_balance_df()

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_balance_sheet("AAPL", freq="quarterly")

        assert "# Balance Sheet data for AAPL (quarterly)" in result
        assert "Total Assets" in result

    def test_annual_balance_sheet_success(self):
        from tradingagents.dataflows.y_finance import get_balance_sheet

        mock_ticker = MagicMock()
        mock_ticker.balance_sheet = self._mock_balance_df()

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_balance_sheet("AAPL", freq="annual")

        assert "# Balance Sheet data for AAPL (annual)" in result

    def test_empty_dataframe_returns_no_data_message(self):
        from tradingagents.dataflows.y_finance import get_balance_sheet

        mock_ticker = MagicMock()
        mock_ticker.quarterly_balance_sheet = pd.DataFrame()

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_balance_sheet("AAPL")

        assert "No balance sheet data" in result

    def test_exception_returns_error_string(self):
        from tradingagents.dataflows.y_finance import get_balance_sheet

        mock_ticker = MagicMock()
        type(mock_ticker).quarterly_balance_sheet = PropertyMock(
            side_effect=ConnectionError("network error")
        )

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_balance_sheet("AAPL")

        assert "Error" in result


# ---------------------------------------------------------------------------
# get_cashflow
# ---------------------------------------------------------------------------

class TestGetCashflow:
    """Tests for yfinance get_cashflow."""

    def _mock_cashflow_df(self):
        return pd.DataFrame(
            {"2023-12-31": [500_000]},
            index=["Free Cash Flow"],
        )

    def test_quarterly_cashflow_success(self):
        from tradingagents.dataflows.y_finance import get_cashflow

        mock_ticker = MagicMock()
        mock_ticker.quarterly_cashflow = self._mock_cashflow_df()

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_cashflow("AAPL", freq="quarterly")

        assert "# Cash Flow data for AAPL (quarterly)" in result
        assert "Free Cash Flow" in result

    def test_empty_dataframe_returns_no_data_message(self):
        from tradingagents.dataflows.y_finance import get_cashflow

        mock_ticker = MagicMock()
        mock_ticker.quarterly_cashflow = pd.DataFrame()

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_cashflow("AAPL")

        assert "No cash flow data" in result

    def test_exception_returns_error_string(self):
        from tradingagents.dataflows.y_finance import get_cashflow

        mock_ticker = MagicMock()
        type(mock_ticker).quarterly_cashflow = PropertyMock(
            side_effect=ConnectionError("network error")
        )

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_cashflow("AAPL")

        assert "Error" in result


# ---------------------------------------------------------------------------
# get_income_statement
# ---------------------------------------------------------------------------

class TestGetIncomeStatement:
    """Tests for yfinance get_income_statement."""

    def _mock_income_df(self):
        return pd.DataFrame(
            {"2023-12-31": [400_000]},
            index=["Total Revenue"],
        )

    def test_quarterly_income_statement_success(self):
        from tradingagents.dataflows.y_finance import get_income_statement

        mock_ticker = MagicMock()
        mock_ticker.quarterly_income_stmt = self._mock_income_df()

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_income_statement("AAPL", freq="quarterly")

        assert "# Income Statement data for AAPL (quarterly)" in result
        assert "Total Revenue" in result

    def test_empty_dataframe_returns_no_data_message(self):
        from tradingagents.dataflows.y_finance import get_income_statement

        mock_ticker = MagicMock()
        mock_ticker.quarterly_income_stmt = pd.DataFrame()

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_income_statement("AAPL")

        assert "No income statement data" in result


# ---------------------------------------------------------------------------
# get_insider_transactions
# ---------------------------------------------------------------------------

class TestGetInsiderTransactions:
    """Tests for yfinance get_insider_transactions."""

    def _mock_insider_df(self):
        return pd.DataFrame(
            {
                "Date": ["2024-01-15"],
                "Insider": ["Tim Cook"],
                "Transaction": ["Sale"],
                "Shares": [10000],
                "Value": [1_500_000],
            }
        )

    def test_returns_csv_string_with_header(self):
        from tradingagents.dataflows.y_finance import get_insider_transactions

        mock_ticker = MagicMock()
        mock_ticker.insider_transactions = self._mock_insider_df()

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_insider_transactions("AAPL")

        assert "# Insider Transactions data for AAPL" in result
        assert "Tim Cook" in result

    def test_none_data_returns_no_data_message(self):
        from tradingagents.dataflows.y_finance import get_insider_transactions

        mock_ticker = MagicMock()
        mock_ticker.insider_transactions = None

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_insider_transactions("AAPL")

        assert "No insider transactions data" in result

    def test_empty_dataframe_returns_no_data_message(self):
        from tradingagents.dataflows.y_finance import get_insider_transactions

        mock_ticker = MagicMock()
        mock_ticker.insider_transactions = pd.DataFrame()

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_insider_transactions("AAPL")

        assert "No insider transactions data" in result

    def test_exception_returns_error_string(self):
        from tradingagents.dataflows.y_finance import get_insider_transactions

        mock_ticker = MagicMock()
        type(mock_ticker).insider_transactions = PropertyMock(
            side_effect=ConnectionError("network error")
        )

        with patch("tradingagents.dataflows.y_finance.yf.Ticker", return_value=mock_ticker):
            result = get_insider_transactions("AAPL")

        assert "Error" in result


# ---------------------------------------------------------------------------
# get_stock_stats_indicators_window
# ---------------------------------------------------------------------------

class TestGetStockStatsIndicatorsWindow:
    """Tests for get_stock_stats_indicators_window (technical indicators)."""

    def _bulk_rsi_data(self):
        """Return a realistic dict of date→rsi_value as _get_stock_stats_bulk would."""
        return {
            "2024-01-08": "62.34",
            "2024-01-07": "N/A",       # weekend
            "2024-01-06": "N/A",       # weekend
            "2024-01-05": "59.12",
            "2024-01-04": "55.67",
            "2024-01-03": "50.00",
        }

    def test_returns_formatted_indicator_string(self):
        """Success path: returns a multi-line string with dates and RSI values."""
        from tradingagents.dataflows.y_finance import get_stock_stats_indicators_window

        with patch(
            "tradingagents.dataflows.y_finance._get_stock_stats_bulk",
            return_value=self._bulk_rsi_data(),
        ):
            result = get_stock_stats_indicators_window("AAPL", "rsi", "2024-01-08", 5)

        assert "rsi" in result
        assert "2024-01-08" in result
        assert "62.34" in result

    def test_includes_indicator_description(self):
        """The returned string includes the indicator description / usage notes."""
        from tradingagents.dataflows.y_finance import get_stock_stats_indicators_window

        with patch(
            "tradingagents.dataflows.y_finance._get_stock_stats_bulk",
            return_value=self._bulk_rsi_data(),
        ):
            result = get_stock_stats_indicators_window("AAPL", "rsi", "2024-01-08", 5)

        # Every supported indicator has a description string
        assert "RSI" in result or "momentum" in result.lower()

    def test_unsupported_indicator_raises_value_error(self):
        """Requesting an unsupported indicator raises ValueError before any network call."""
        from tradingagents.dataflows.y_finance import get_stock_stats_indicators_window

        with pytest.raises(ValueError, match="not supported"):
            get_stock_stats_indicators_window("AAPL", "unknown_indicator", "2024-01-08", 5)

    def test_bulk_exception_triggers_fallback(self):
        """If _get_stock_stats_bulk raises, the function falls back gracefully."""
        from tradingagents.dataflows.y_finance import get_stock_stats_indicators_window

        with patch(
            "tradingagents.dataflows.y_finance._get_stock_stats_bulk",
            side_effect=Exception("stockstats unavailable"),
        ):
            with patch(
                "tradingagents.dataflows.y_finance.get_stockstats_indicator",
                return_value="45.00",
            ):
                result = get_stock_stats_indicators_window("AAPL", "rsi", "2024-01-08", 3)

        assert isinstance(result, str)
        assert "rsi" in result


# ---------------------------------------------------------------------------
# get_global_news_yfinance
# ---------------------------------------------------------------------------

class TestGetGlobalNewsYfinance:
    """Tests for get_global_news_yfinance."""

    def _mock_search_with_article(self):
        """Return a mock yf.Search object with one flat-structured news article."""
        mock_search = MagicMock()
        mock_search.news = [
            {
                "title": "Fed Holds Rates Steady",
                "publisher": "Reuters",
                "link": "https://example.com/fed",
                "summary": "The Federal Reserve decided to hold interest rates.",
            }
        ]
        return mock_search

    def test_returns_string_with_articles(self):
        """When yfinance Search returns articles, a formatted string is returned."""
        from tradingagents.dataflows.yfinance_news import get_global_news_yfinance

        with patch(
            "tradingagents.dataflows.yfinance_news.yf.Search",
            return_value=self._mock_search_with_article(),
        ):
            result = get_global_news_yfinance("2024-01-15", look_back_days=7)

        assert isinstance(result, str)
        assert "Fed Holds Rates Steady" in result

    def test_no_news_returns_fallback_message(self):
        """When no articles are found, a 'no news found' message is returned."""
        from tradingagents.dataflows.yfinance_news import get_global_news_yfinance

        mock_search = MagicMock()
        mock_search.news = []

        with patch(
            "tradingagents.dataflows.yfinance_news.yf.Search",
            return_value=mock_search,
        ):
            result = get_global_news_yfinance("2024-01-15")

        assert "No global news found" in result

    def test_handles_nested_content_structure(self):
        """Articles with nested 'content' key are parsed correctly."""
        from tradingagents.dataflows.yfinance_news import get_global_news_yfinance

        mock_search = MagicMock()
        mock_search.news = [
            {
                "content": {
                    "title": "Inflation Report Beats Expectations",
                    "summary": "CPI data came in below forecasts.",
                    "provider": {"displayName": "Bloomberg"},
                    "canonicalUrl": {"url": "https://bloomberg.com/story"},
                    "pubDate": "2024-01-15T10:00:00Z",
                }
            }
        ]

        with patch(
            "tradingagents.dataflows.yfinance_news.yf.Search",
            return_value=mock_search,
        ):
            result = get_global_news_yfinance("2024-01-15", look_back_days=3)

        assert "Inflation Report Beats Expectations" in result

    def test_deduplicates_articles_across_queries(self):
        """Duplicate titles from multiple search queries appear only once."""
        from tradingagents.dataflows.yfinance_news import get_global_news_yfinance

        same_article = {"title": "Market Rally Continues", "publisher": "AP", "link": ""}

        mock_search = MagicMock()
        mock_search.news = [same_article]

        with patch(
            "tradingagents.dataflows.yfinance_news.yf.Search",
            return_value=mock_search,
        ):
            result = get_global_news_yfinance("2024-01-15", look_back_days=7, limit=5)

        # Title should appear exactly once despite multiple search queries
        assert result.count("Market Rally Continues") == 1
