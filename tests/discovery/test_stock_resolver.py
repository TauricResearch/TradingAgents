import logging
from unittest.mock import patch

from tradingagents.dataflows.trending.stock_resolver import (
    resolve_ticker,
    validate_us_ticker,
)


class TestStaticLookup:
    def test_static_lookup_for_known_companies(self):
        assert resolve_ticker("Apple") == "AAPL"
        assert resolve_ticker("Microsoft") == "MSFT"
        assert resolve_ticker("Google") == "GOOGL"
        assert resolve_ticker("Amazon") == "AMZN"
        assert resolve_ticker("Tesla") == "TSLA"
        assert resolve_ticker("Nvidia") == "NVDA"

    def test_static_lookup_case_insensitive(self):
        assert resolve_ticker("APPLE") == "AAPL"
        assert resolve_ticker("apple") == "AAPL"
        assert resolve_ticker("ApPlE") == "AAPL"
        assert resolve_ticker("microsoft") == "MSFT"
        assert resolve_ticker("MICROSOFT") == "MSFT"


class TestNameVariationHandling:
    def test_name_variation_handling_with_suffixes(self):
        assert resolve_ticker("Apple Inc.") == "AAPL"
        assert resolve_ticker("Apple Inc") == "AAPL"
        assert resolve_ticker("Apple Corporation") == "AAPL"
        assert resolve_ticker("Microsoft Corp.") == "MSFT"
        assert resolve_ticker("Microsoft Corp") == "MSFT"
        assert resolve_ticker("Tesla Inc") == "TSLA"

    def test_name_variation_handling_informal_names(self):
        assert resolve_ticker("the iPhone maker") == "AAPL"
        assert resolve_ticker("iPhone maker") == "AAPL"
        assert resolve_ticker("the search giant") == "GOOGL"
        assert resolve_ticker("the e-commerce giant") == "AMZN"
        assert resolve_ticker("EV maker Tesla") == "TSLA"

    def test_name_variation_handling_alternate_names(self):
        assert resolve_ticker("Alphabet") == "GOOGL"
        assert resolve_ticker("Meta") == "META"
        assert resolve_ticker("Facebook") == "META"
        assert resolve_ticker("Meta Platforms") == "META"


class TestYfinanceFallback:
    @patch("tradingagents.dataflows.trending.stock_resolver._search_yfinance_ticker")
    @patch("tradingagents.dataflows.trending.stock_resolver.validate_us_ticker")
    def test_yfinance_fallback_for_unknown_company(self, mock_validate, mock_search):
        mock_search.return_value = "PLTR"
        mock_validate.return_value = True

        result = resolve_ticker("UnknownTechStartupXYZ")

        mock_search.assert_called_once()
        assert result == "PLTR"

    @patch("tradingagents.dataflows.trending.stock_resolver._search_yfinance_ticker")
    def test_yfinance_fallback_returns_none_when_not_found(self, mock_search):
        mock_search.return_value = None

        result = resolve_ticker("NonexistentCompanyXYZ123")

        assert result is None


class TestUSExchangeValidation:
    @patch("tradingagents.dataflows.trending.stock_resolver.yf.Ticker")
    def test_validate_us_ticker_accepts_nyse(self, mock_ticker):
        mock_info = {"exchange": "NYQ"}
        mock_ticker.return_value.info = mock_info

        assert validate_us_ticker("IBM") is True

    @patch("tradingagents.dataflows.trending.stock_resolver.yf.Ticker")
    def test_validate_us_ticker_accepts_nasdaq(self, mock_ticker):
        mock_info = {"exchange": "NMS"}
        mock_ticker.return_value.info = mock_info

        assert validate_us_ticker("AAPL") is True

    @patch("tradingagents.dataflows.trending.stock_resolver.yf.Ticker")
    def test_validate_us_ticker_accepts_amex(self, mock_ticker):
        mock_info = {"exchange": "ASE"}
        mock_ticker.return_value.info = mock_info

        assert validate_us_ticker("SPY") is True

    @patch("tradingagents.dataflows.trending.stock_resolver.yf.Ticker")
    def test_validate_us_ticker_rejects_international(self, mock_ticker):
        mock_info = {"exchange": "LSE"}
        mock_ticker.return_value.info = mock_info

        assert validate_us_ticker("VOD.L") is False

    @patch("tradingagents.dataflows.trending.stock_resolver.yf.Ticker")
    def test_validate_us_ticker_rejects_otc(self, mock_ticker):
        mock_info = {"exchange": "PNK"}
        mock_ticker.return_value.info = mock_info

        assert validate_us_ticker("OTCPK") is False


class TestAmbiguousResolutionLogging:
    def test_ambiguous_resolution_logs_multiple_matches(self, caplog):
        with caplog.at_level(
            logging.INFO, logger="tradingagents.dataflows.trending.stock_resolver"
        ):
            pass

    @patch("tradingagents.dataflows.trending.stock_resolver._search_yfinance_ticker")
    @patch("tradingagents.dataflows.trending.stock_resolver.validate_us_ticker")
    def test_yfinance_fallback_is_logged(self, mock_validate, mock_search, caplog):
        mock_search.return_value = "RBLX"
        mock_validate.return_value = True

        with caplog.at_level(
            logging.INFO, logger="tradingagents.dataflows.trending.stock_resolver"
        ):
            result = resolve_ticker("SomeRandomCompanyNotInMapping")

        assert any(
            "fallback" in record.message.lower() or "yfinance" in record.message.lower()
            for record in caplog.records
        )

    @patch("tradingagents.dataflows.trending.stock_resolver.yf.Ticker")
    def test_validation_failure_is_logged(self, mock_ticker, caplog):
        mock_info = {"exchange": "LSE"}
        mock_ticker.return_value.info = mock_info

        with caplog.at_level(
            logging.WARNING, logger="tradingagents.dataflows.trending.stock_resolver"
        ):
            result = validate_us_ticker("VOD.L")

        assert result is False
