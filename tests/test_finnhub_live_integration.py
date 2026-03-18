"""Live integration tests for the Finnhub dataflow modules.

These tests make REAL HTTP requests to the Finnhub API and therefore require
a valid ``FINNHUB_API_KEY`` environment variable.  When the key is absent the
entire module is skipped automatically.

## Free-tier vs paid-tier endpoints (confirmed by live testing 2026-03-18)

FREE TIER (60 calls/min):
    /quote                      ✅ get_quote, market movers/indices/sectors
    /stock/profile2             ✅ get_company_profile
    /stock/metric               ✅ get_basic_financials
    /company-news               ✅ get_company_news
    /news                       ✅ get_market_news, get_topic_news
    /stock/insider-transactions ✅ get_insider_transactions

PAID TIER (returns HTTP 403):
    /stock/candle               ❌ get_stock_candles
    /financials-reported        ❌ get_financial_statements (XBRL as-filed)
    /indicator                  ❌ get_indicator_finnhub (SMA, EMA, MACD, RSI, BBANDS, ATR)

Run only the live tests:
    FINNHUB_API_KEY=<your_key> pytest tests/test_finnhub_live_integration.py -v -m integration

Run only free-tier tests:
    FINNHUB_API_KEY=<your_key> pytest tests/test_finnhub_live_integration.py -v -m "integration and not paid_tier"

Skip them in CI (default behaviour when the env var is not set):
    pytest tests/ -v  # live tests auto-skip
"""

import os

import pytest


# ---------------------------------------------------------------------------
# Global skip guard — skip every test in this file if no API key is present.
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.integration

_FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")

_skip_if_no_key = pytest.mark.skipif(
    not _FINNHUB_API_KEY,
    reason="FINNHUB_API_KEY env var not set — skipping live Finnhub tests",
)

# Mark tests that require a paid Finnhub subscription (confirmed HTTP 403 on free tier)
_paid_tier = pytest.mark.paid_tier

# Stable, well-covered symbol used across all tests
_SYMBOL = "AAPL"
_START_DATE = "2024-01-02"
_END_DATE = "2024-01-05"


# ---------------------------------------------------------------------------
# 1. finnhub_common
# ---------------------------------------------------------------------------


@_skip_if_no_key
class TestLiveGetApiKey:
    """Live smoke tests for the key-retrieval helper."""

    def test_returns_non_empty_string(self):
        from tradingagents.dataflows.finnhub_common import get_api_key

        key = get_api_key()
        assert isinstance(key, str)
        assert len(key) > 0


@_skip_if_no_key
class TestLiveMakeApiRequest:
    """Live smoke test for the HTTP request helper."""

    def test_quote_endpoint_returns_dict(self):
        from tradingagents.dataflows.finnhub_common import _make_api_request

        result = _make_api_request("quote", {"symbol": _SYMBOL})
        assert isinstance(result, dict)
        # Finnhub quote always returns these keys
        assert "c" in result  # current price
        assert "pc" in result  # previous close


# ---------------------------------------------------------------------------
# 2. finnhub_stock
# ---------------------------------------------------------------------------


@_skip_if_no_key
@_paid_tier
@pytest.mark.skip(reason="Requires paid Finnhub tier — /stock/candle returns HTTP 403 on free tier")
class TestLiveGetStockCandles:
    """Live smoke tests for OHLCV candle retrieval (PAID TIER ONLY)."""

    def test_returns_csv_string(self):
        from tradingagents.dataflows.finnhub_stock import get_stock_candles

        result = get_stock_candles(_SYMBOL, _START_DATE, _END_DATE)
        assert isinstance(result, str)

    def test_csv_has_header_row(self):
        from tradingagents.dataflows.finnhub_stock import get_stock_candles

        result = get_stock_candles(_SYMBOL, _START_DATE, _END_DATE)
        first_line = result.strip().split("\n")[0]
        assert first_line == "timestamp,open,high,low,close,volume"

    def test_csv_contains_data_rows(self):
        from tradingagents.dataflows.finnhub_stock import get_stock_candles

        result = get_stock_candles(_SYMBOL, _START_DATE, _END_DATE)
        lines = [l for l in result.strip().split("\n") if l]
        # At minimum the header + at least one trading day
        assert len(lines) >= 2

    def test_invalid_symbol_raises_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError
        from tradingagents.dataflows.finnhub_stock import get_stock_candles

        with pytest.raises(FinnhubError):
            get_stock_candles("ZZZZZ_INVALID_TICKER", _START_DATE, _END_DATE)


@_skip_if_no_key
class TestLiveGetQuote:
    """Live smoke tests for real-time quote retrieval."""

    def test_returns_dict_with_expected_keys(self):
        from tradingagents.dataflows.finnhub_stock import get_quote

        result = get_quote(_SYMBOL)
        expected_keys = {
            "symbol", "current_price", "change", "change_percent",
            "high", "low", "open", "prev_close", "timestamp",
        }
        assert expected_keys == set(result.keys())

    def test_symbol_field_matches_requested_symbol(self):
        from tradingagents.dataflows.finnhub_stock import get_quote

        result = get_quote(_SYMBOL)
        assert result["symbol"] == _SYMBOL

    def test_current_price_is_positive_float(self):
        from tradingagents.dataflows.finnhub_stock import get_quote

        result = get_quote(_SYMBOL)
        assert isinstance(result["current_price"], float)
        assert result["current_price"] > 0


# ---------------------------------------------------------------------------
# 3. finnhub_fundamentals
# ---------------------------------------------------------------------------


@_skip_if_no_key
class TestLiveGetCompanyProfile:
    """Live smoke tests for company profile retrieval."""

    def test_returns_non_empty_string(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_company_profile

        result = get_company_profile(_SYMBOL)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_output_contains_symbol(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_company_profile

        result = get_company_profile(_SYMBOL)
        assert _SYMBOL in result

    def test_output_contains_company_name(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_company_profile

        result = get_company_profile(_SYMBOL)
        # Apple appears under various name variants; just check 'Apple' is present
        assert "Apple" in result


@_skip_if_no_key
@_paid_tier
@pytest.mark.skip(reason="Requires paid Finnhub tier — /financials-reported returns HTTP 403 on free tier")
class TestLiveGetFinancialStatements:
    """Live smoke tests for XBRL as-filed financial statements (PAID TIER ONLY)."""

    def test_income_statement_returns_non_empty_string(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_financial_statements

        result = get_financial_statements(_SYMBOL, "income_statement", "quarterly")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_balance_sheet_returns_string(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_financial_statements

        result = get_financial_statements(_SYMBOL, "balance_sheet", "quarterly")
        assert isinstance(result, str)

    def test_cash_flow_returns_string(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_financial_statements

        result = get_financial_statements(_SYMBOL, "cash_flow", "quarterly")
        assert isinstance(result, str)

    def test_output_contains_symbol(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_financial_statements

        result = get_financial_statements(_SYMBOL, "income_statement", "quarterly")
        assert _SYMBOL in result


@_skip_if_no_key
class TestLiveGetBasicFinancials:
    """Live smoke tests for key financial metrics retrieval."""

    def test_returns_non_empty_string(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_basic_financials

        result = get_basic_financials(_SYMBOL)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_output_contains_valuation_section(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_basic_financials

        result = get_basic_financials(_SYMBOL)
        assert "Valuation" in result

    def test_output_contains_pe_metric(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_basic_financials

        result = get_basic_financials(_SYMBOL)
        assert "P/E" in result


# ---------------------------------------------------------------------------
# 4. finnhub_news
# ---------------------------------------------------------------------------


@_skip_if_no_key
class TestLiveGetCompanyNews:
    """Live smoke tests for company-specific news retrieval."""

    def test_returns_non_empty_string(self):
        from tradingagents.dataflows.finnhub_news import get_company_news

        result = get_company_news(_SYMBOL, _START_DATE, _END_DATE)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_output_contains_symbol(self):
        from tradingagents.dataflows.finnhub_news import get_company_news

        result = get_company_news(_SYMBOL, _START_DATE, _END_DATE)
        assert _SYMBOL in result


@_skip_if_no_key
class TestLiveGetMarketNews:
    """Live smoke tests for broad market news retrieval."""

    def test_general_news_returns_string(self):
        from tradingagents.dataflows.finnhub_news import get_market_news

        result = get_market_news("general")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_output_contains_market_news_header(self):
        from tradingagents.dataflows.finnhub_news import get_market_news

        result = get_market_news("general")
        assert "Market News" in result

    def test_crypto_category_accepted(self):
        from tradingagents.dataflows.finnhub_news import get_market_news

        result = get_market_news("crypto")
        assert isinstance(result, str)


@_skip_if_no_key
class TestLiveGetInsiderTransactions:
    """Live smoke tests for insider transaction retrieval."""

    def test_returns_non_empty_string(self):
        from tradingagents.dataflows.finnhub_news import get_insider_transactions

        result = get_insider_transactions(_SYMBOL)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_output_contains_symbol(self):
        from tradingagents.dataflows.finnhub_news import get_insider_transactions

        result = get_insider_transactions(_SYMBOL)
        assert _SYMBOL in result


# ---------------------------------------------------------------------------
# 5. finnhub_scanner
# ---------------------------------------------------------------------------


@_skip_if_no_key
class TestLiveGetMarketMovers:
    """Live smoke tests for market movers (may be slow — fetches 50 quotes)."""

    def test_gainers_returns_markdown_table(self):
        from tradingagents.dataflows.finnhub_scanner import get_market_movers_finnhub

        result = get_market_movers_finnhub("gainers")
        assert isinstance(result, str)
        assert "Symbol" in result or "symbol" in result.lower()

    def test_losers_returns_markdown_table(self):
        from tradingagents.dataflows.finnhub_scanner import get_market_movers_finnhub

        result = get_market_movers_finnhub("losers")
        assert isinstance(result, str)

    def test_active_returns_markdown_table(self):
        from tradingagents.dataflows.finnhub_scanner import get_market_movers_finnhub

        result = get_market_movers_finnhub("active")
        assert isinstance(result, str)


@_skip_if_no_key
class TestLiveGetMarketIndices:
    """Live smoke tests for market index levels."""

    def test_returns_string_with_indices_header(self):
        from tradingagents.dataflows.finnhub_scanner import get_market_indices_finnhub

        result = get_market_indices_finnhub()
        assert isinstance(result, str)
        assert "Major Market Indices" in result

    def test_output_contains_sp500_proxy(self):
        from tradingagents.dataflows.finnhub_scanner import get_market_indices_finnhub

        result = get_market_indices_finnhub()
        assert "SPY" in result or "S&P 500" in result


@_skip_if_no_key
class TestLiveGetSectorPerformance:
    """Live smoke tests for sector performance."""

    def test_returns_sector_performance_string(self):
        from tradingagents.dataflows.finnhub_scanner import get_sector_performance_finnhub

        result = get_sector_performance_finnhub()
        assert isinstance(result, str)
        assert "Sector Performance" in result

    def test_output_contains_at_least_one_etf(self):
        from tradingagents.dataflows.finnhub_scanner import get_sector_performance_finnhub

        result = get_sector_performance_finnhub()
        etf_tickers = {"XLK", "XLV", "XLF", "XLE", "XLY", "XLP", "XLI", "XLB", "XLRE", "XLU", "XLC"}
        assert any(t in result for t in etf_tickers)


@_skip_if_no_key
class TestLiveGetTopicNews:
    """Live smoke tests for topic-based news."""

    def test_market_topic_returns_string(self):
        from tradingagents.dataflows.finnhub_scanner import get_topic_news_finnhub

        result = get_topic_news_finnhub("market")
        assert isinstance(result, str)

    def test_crypto_topic_returns_string(self):
        from tradingagents.dataflows.finnhub_scanner import get_topic_news_finnhub

        result = get_topic_news_finnhub("crypto")
        assert isinstance(result, str)
        assert "crypto" in result.lower()


# ---------------------------------------------------------------------------
# 6. finnhub_indicators
# ---------------------------------------------------------------------------


@_skip_if_no_key
@_paid_tier
@pytest.mark.skip(reason="Requires paid Finnhub tier — /indicator returns HTTP 403 on free tier")
class TestLiveGetIndicatorFinnhub:
    """Live smoke tests for technical indicators (PAID TIER ONLY)."""

    def test_rsi_returns_string(self):
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        result = get_indicator_finnhub(_SYMBOL, "rsi", "2023-10-01", _END_DATE)
        assert isinstance(result, str)
        assert "RSI" in result

    def test_macd_returns_string_with_columns(self):
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        result = get_indicator_finnhub(_SYMBOL, "macd", "2023-10-01", _END_DATE)
        assert isinstance(result, str)
        assert "MACD" in result
        assert "Signal" in result

    def test_bbands_returns_string_with_band_columns(self):
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        result = get_indicator_finnhub(_SYMBOL, "bbands", "2023-10-01", _END_DATE)
        assert isinstance(result, str)
        assert "Upper" in result
        assert "Lower" in result

    def test_sma_returns_string(self):
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        result = get_indicator_finnhub(_SYMBOL, "sma", "2023-10-01", _END_DATE, time_period=20)
        assert isinstance(result, str)
        assert "SMA" in result

    def test_ema_returns_string(self):
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        result = get_indicator_finnhub(_SYMBOL, "ema", "2023-10-01", _END_DATE, time_period=12)
        assert isinstance(result, str)
        assert "EMA" in result

    def test_atr_returns_string(self):
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        result = get_indicator_finnhub(_SYMBOL, "atr", "2023-10-01", _END_DATE, time_period=14)
        assert isinstance(result, str)
        assert "ATR" in result
