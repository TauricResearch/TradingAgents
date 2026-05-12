"""Unit tests for Tushare data source and news service modules."""

import os
from unittest.mock import patch, MagicMock

import pytest
import pandas as pd

from tradingagents.dataflows.interface import detect_vendor_for_ticker
from tradingagents.dataflows.tushare_data import (
    convert_date_to_tushare,
    convert_date_from_tushare,
    normalize_ts_code,
)


# ---------------------------------------------------------------------------
# 1. Ticker format detection tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectVendorForTicker:
    """Test ticker format detection for auto-routing."""

    def test_a_share_sh_suffix(self):
        """600000.SH should route to akshare"""
        assert detect_vendor_for_ticker("600000.SH") == "akshare"

    def test_a_share_sz_suffix(self):
        """000001.SZ should route to akshare"""
        assert detect_vendor_for_ticker("000001.SZ") == "akshare"

    def test_a_share_sh_prefix(self):
        """SH600000 should route to akshare"""
        assert detect_vendor_for_ticker("SH600000") == "akshare"

    def test_a_share_sz_prefix(self):
        """SZ000001 should route to akshare"""
        assert detect_vendor_for_ticker("SZ000001") == "akshare"

    def test_a_share_pure_digits(self):
        """600000 (6-digit) should route to akshare"""
        assert detect_vendor_for_ticker("600000") == "akshare"

    def test_hk_stock_suffix(self):
        """0700.HK should route to akshare"""
        assert detect_vendor_for_ticker("0700.HK") == "akshare"

    def test_hk_stock_prefix(self):
        """HK0700 should route to akshare"""
        assert detect_vendor_for_ticker("HK0700") == "akshare"

    def test_us_stock(self):
        """AAPL should return None (use default)"""
        assert detect_vendor_for_ticker("AAPL") is None

    def test_us_stock_with_dot(self):
        """BRK.B should return None"""
        assert detect_vendor_for_ticker("BRK.B") is None

    def test_empty_string(self):
        assert detect_vendor_for_ticker("") is None

    def test_none(self):
        assert detect_vendor_for_ticker(None) is None

    def test_a_share_ss_suffix(self):
        """600000.SS (yfinance convention) should route to akshare"""
        assert detect_vendor_for_ticker("600000.SS") == "akshare"

    def test_a_share_ss_prefix(self):
        """SS600000 should route to akshare"""
        assert detect_vendor_for_ticker("SS600000") == "akshare"

    def test_case_insensitive(self):
        """Should handle lowercase"""
        assert detect_vendor_for_ticker("sh600000") == "akshare"
        assert detect_vendor_for_ticker("600000.sh") == "akshare"
        assert detect_vendor_for_ticker("600000.ss") == "akshare"


# ---------------------------------------------------------------------------
# 2. Date conversion tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDateConversion:
    """Test date format conversion between standard and Tushare format."""

    def test_to_tushare_format(self):
        assert convert_date_to_tushare("2024-01-15") == "20240115"
        assert convert_date_to_tushare("2023-12-31") == "20231231"

    def test_from_tushare_format(self):
        assert convert_date_from_tushare("20240115") == "2024-01-15"
        assert convert_date_from_tushare("20231231") == "2023-12-31"

    def test_from_tushare_non_8_digit(self):
        """Non-8-digit strings should pass through unchanged."""
        assert convert_date_from_tushare("2024-01-15") == "2024-01-15"


# ---------------------------------------------------------------------------
# 3. Ticker normalization tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeTsCode:
    """Test normalization of various ticker formats to Tushare ts_code."""

    def test_pure_digits_sh(self):
        """6开头 → 上海"""
        assert normalize_ts_code("600000") == "600000.SH"

    def test_pure_digits_sz(self):
        """0/3开头 → 深圳"""
        assert normalize_ts_code("000001") == "000001.SZ"
        assert normalize_ts_code("300001") == "300001.SZ"

    def test_prefix_format(self):
        assert normalize_ts_code("SH600000") == "600000.SH"
        assert normalize_ts_code("SZ000001") == "000001.SZ"

    def test_suffix_format_passthrough(self):
        assert normalize_ts_code("600000.SH") == "600000.SH"
        assert normalize_ts_code("000001.SZ") == "000001.SZ"

    def test_hk_stock(self):
        assert normalize_ts_code("HK0700") == "0700.HK"
        assert normalize_ts_code("0700.HK") == "0700.HK"

    def test_ss_suffix_converted_to_sh(self):
        """600000.SS (yfinance convention) should convert to 600000.SH"""
        assert normalize_ts_code("600000.SS") == "600000.SH"

    def test_ss_prefix_converted_to_sh(self):
        """SS600000 should convert to 600000.SH"""
        assert normalize_ts_code("SS600000") == "600000.SH"

    def test_lowercase_normalized(self):
        """Lowercase input should be uppercased in output."""
        assert normalize_ts_code("sh600000") == "600000.SH"
        assert normalize_ts_code("sz000001") == "000001.SZ"


# ---------------------------------------------------------------------------
# 4. Mock Tushare stock data retrieval tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetTushareStock:
    """Test get_tushare_stock with mocked Tushare API."""

    @patch("tradingagents.dataflows.tushare_data.get_tushare_pro")
    def test_returns_csv_format(self, mock_pro):
        """Test that get_tushare_stock returns properly formatted CSV."""
        from tradingagents.dataflows.tushare_data import get_tushare_stock

        mock_api = MagicMock()
        mock_pro.return_value = mock_api

        mock_api.daily.return_value = pd.DataFrame({
            "ts_code": ["600000.SH", "600000.SH"],
            "trade_date": ["20240116", "20240115"],
            "open": [10.50, 10.30],
            "high": [10.80, 10.60],
            "low": [10.20, 10.10],
            "close": [10.60, 10.40],
            "vol": [12345.0, 11234.0],
        })

        mock_api.adj_factor.return_value = pd.DataFrame({
            "ts_code": ["600000.SH", "600000.SH"],
            "trade_date": ["20240116", "20240115"],
            "adj_factor": [120.5, 120.0],
        })

        result = get_tushare_stock("600000.SH", "2024-01-15", "2024-01-16")

        assert "# Stock data for" in result
        assert "Date,Open,High,Low,Close,Adj Close,Volume" in result
        assert "2024-01-15" in result
        assert "2024-01-16" in result

    @patch("tradingagents.dataflows.tushare_data.get_tushare_pro")
    def test_empty_data(self, mock_pro):
        """Test handling of empty data."""
        from tradingagents.dataflows.tushare_data import get_tushare_stock

        mock_api = MagicMock()
        mock_pro.return_value = mock_api
        mock_api.daily.return_value = pd.DataFrame()

        result = get_tushare_stock("600000.SH", "2024-01-15", "2024-01-16")
        assert "No stock data found" in result or "Error" in result

    @patch("tradingagents.dataflows.tushare_data.get_tushare_pro")
    def test_no_adj_factor(self, mock_pro):
        """Test handling when adj_factor returns empty."""
        from tradingagents.dataflows.tushare_data import get_tushare_stock

        mock_api = MagicMock()
        mock_pro.return_value = mock_api

        mock_api.daily.return_value = pd.DataFrame({
            "ts_code": ["600000.SH"],
            "trade_date": ["20240115"],
            "open": [10.30],
            "high": [10.60],
            "low": [10.10],
            "close": [10.40],
            "vol": [11234.0],
        })
        mock_api.adj_factor.return_value = pd.DataFrame()

        result = get_tushare_stock("600000.SH", "2024-01-15", "2024-01-15")

        # adj_close should fall back to close
        assert "Date,Open,High,Low,Close,Adj Close,Volume" in result
        assert "2024-01-15" in result


# ---------------------------------------------------------------------------
# 5. Mock news service tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNewsService:
    """Test news service with mocked HTTP calls."""

    @patch("tradingagents.dataflows.news_service.requests.get")
    def test_get_news_returns_formatted(self, mock_get):
        """Test news service returns properly formatted output."""
        from tradingagents.dataflows.news_service import get_news_service_news

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [{
                "title": "测试新闻标题",
                "summary": "这是一条测试新闻摘要",
                "source_name": "财联社",
                "url": "https://example.com/news/1",
                "published_at": "2024-01-15T10:00:00+08:00",
            }],
        }
        mock_get.return_value = mock_response

        with patch.dict(os.environ, {"NEWS_SERVER_API_KEY": "test_key"}):
            result = get_news_service_news("600519.SH", "2024-01-15", "2024-01-16")

        assert "News" in result
        assert "测试新闻标题" in result
        assert "财联社" in result

    def test_no_api_key_graceful(self):
        """Test graceful handling when API key is not configured."""
        from tradingagents.dataflows.news_service import get_news_service_news

        with patch.dict(os.environ, {"NEWS_SERVER_API_KEY": ""}, clear=False):
            result = get_news_service_news("600519.SH", "2024-01-15", "2024-01-16")

        # Should not crash, should return appropriate message
        assert "No news" in result or "not configured" in result.lower() or "error" in result.lower()

    @patch("tradingagents.dataflows.news_service.requests.get")
    def test_connection_error_graceful(self, mock_get):
        """Test graceful handling of connection errors."""
        import requests as req
        from tradingagents.dataflows.news_service import get_news_service_news

        mock_get.side_effect = req.exceptions.ConnectionError("Connection refused")

        with patch.dict(os.environ, {"NEWS_SERVER_API_KEY": "test_key"}):
            result = get_news_service_news("600519.SH", "2024-01-15", "2024-01-16")

        # Both calls to _make_request will fail, so we expect either no news or error
        assert "No news" in result or "Error" in result or "error" in result.lower()


# ---------------------------------------------------------------------------
# 6. Auto-routing tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAutoRouting:
    """Test auto-routing logic based on ticker format."""

    def test_a_share_routes_to_akshare(self):
        """A-share ticker should prefer akshare vendor."""
        assert detect_vendor_for_ticker("600000.SH") == "akshare"
        assert detect_vendor_for_ticker("000001.SZ") == "akshare"

    def test_us_stock_does_not_route_to_tushare(self):
        """US stock should not route to tushare."""
        assert detect_vendor_for_ticker("AAPL") is None
        assert detect_vendor_for_ticker("MSFT") is None
        assert detect_vendor_for_ticker("TSLA") is None

    def test_hk_stock_routes_to_akshare(self):
        """HK stock tickers should route to akshare."""
        assert detect_vendor_for_ticker("0700.HK") == "akshare"
        assert detect_vendor_for_ticker("HK0700") == "akshare"
        assert detect_vendor_for_ticker("09988.HK") == "akshare"

    def test_various_sz_formats(self):
        """Various Shenzhen formats should all route to akshare."""
        assert detect_vendor_for_ticker("000001") == "akshare"
        assert detect_vendor_for_ticker("300001") == "akshare"
        assert detect_vendor_for_ticker("SZ000001") == "akshare"
        assert detect_vendor_for_ticker("000001.SZ") == "akshare"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
