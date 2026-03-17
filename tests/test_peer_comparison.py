"""Tests for sector and peer relative performance comparison."""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_price_series(n: int = 130, start: float = 100.0, growth: float = 0.001) -> pd.Series:
    """Create a synthetic daily price series."""
    import numpy as np
    dates = pd.date_range("2025-09-01", periods=n, freq="B")
    prices = [start * (1 + growth) ** i for i in range(n)]
    return pd.Series(prices, index=dates)


# ---------------------------------------------------------------------------
# Unit tests for get_sector_peers
# ---------------------------------------------------------------------------

class TestGetSectorPeers:
    def test_technology_sector_returns_peers(self):
        """get_sector_peers should return known tech tickers for a tech stock."""
        mock_info = {"sector": "Technology"}
        with patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.info = mock_info
            from tradingagents.dataflows.peer_comparison import get_sector_peers
            sector_display, sector_key, peers = get_sector_peers("AAPL")
        assert sector_key == "technology"
        assert len(peers) > 0
        assert "AAPL" not in peers  # ticker excluded from its own peers
        assert any(p in peers for p in ["MSFT", "NVDA", "GOOGL"])

    def test_healthcare_sector(self):
        mock_info = {"sector": "Healthcare"}
        with patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.info = mock_info
            from tradingagents.dataflows.peer_comparison import get_sector_peers
            sector_display, sector_key, peers = get_sector_peers("JNJ")
        assert sector_key == "healthcare"
        assert "JNJ" not in peers

    def test_unknown_sector_returns_empty_peers(self):
        mock_info = {"sector": "Foobar"}
        with patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.info = mock_info
            from tradingagents.dataflows.peer_comparison import get_sector_peers
            sector_display, sector_key, peers = get_sector_peers("XYZ")
        assert peers == []

    def test_network_error_returns_empty(self):
        with patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.info = {}
            mock_ticker.side_effect = Exception("network error")
            from tradingagents.dataflows.peer_comparison import get_sector_peers
            sector_display, sector_key, peers = get_sector_peers("AAPL")
        assert peers == []


# ---------------------------------------------------------------------------
# Unit tests for compute_relative_performance
# ---------------------------------------------------------------------------

class TestComputeRelativePerformance:
    def _mock_download(self, tickers: list[str]) -> pd.DataFrame:
        """Create mock multi-ticker close price DataFrame."""
        n = 130
        data = {}
        for i, t in enumerate(tickers):
            data[t] = _make_price_series(n=n, start=100.0, growth=0.001 * (i + 1))
        df = pd.DataFrame(data, index=pd.date_range("2025-09-01", periods=n, freq="B"))
        return pd.concat({"Close": df}, axis=1)

    def test_returns_markdown_table(self):
        tickers = ["AAPL", "MSFT", "NVDA", "XLK"]
        mock_hist = self._mock_download(tickers)

        with patch("yfinance.download", return_value=mock_hist):
            from tradingagents.dataflows.peer_comparison import compute_relative_performance
            result = compute_relative_performance("AAPL", "technology", ["MSFT", "NVDA", "XLK"])

        assert "| Symbol |" in result
        assert "AAPL" in result
        assert "TARGET" in result

    def test_ticker_appears_as_target(self):
        tickers = ["AAPL", "MSFT", "XLK"]
        mock_hist = self._mock_download(tickers)

        with patch("yfinance.download", return_value=mock_hist):
            from tradingagents.dataflows.peer_comparison import compute_relative_performance
            result = compute_relative_performance("AAPL", "technology", ["MSFT"])

        assert "► TARGET" in result

    def test_etf_appears_as_benchmark(self):
        tickers = ["AAPL", "MSFT", "XLK"]
        mock_hist = self._mock_download(tickers)

        with patch("yfinance.download", return_value=mock_hist):
            from tradingagents.dataflows.peer_comparison import compute_relative_performance
            result = compute_relative_performance("AAPL", "technology", ["MSFT"])

        assert "ETF Benchmark" in result

    def test_alpha_section_present(self):
        tickers = ["AAPL", "XLK"]
        mock_hist = self._mock_download(tickers)

        with patch("yfinance.download", return_value=mock_hist):
            from tradingagents.dataflows.peer_comparison import compute_relative_performance
            result = compute_relative_performance("AAPL", "technology", [])

        assert "Alpha vs Sector ETF" in result

    def test_download_failure_returns_error_string(self):
        with patch("yfinance.download", side_effect=Exception("timeout")):
            from tradingagents.dataflows.peer_comparison import compute_relative_performance
            result = compute_relative_performance("AAPL", "technology", ["MSFT"])
        assert "Error" in result


# ---------------------------------------------------------------------------
# Unit tests for get_sector_relative_report
# ---------------------------------------------------------------------------

class TestGetSectorRelativeReport:
    def _mock_download(self) -> pd.DataFrame:
        n = 130
        data = {
            "AAPL": _make_price_series(n=n, start=150.0, growth=0.002),
            "XLK": _make_price_series(n=n, start=200.0, growth=0.001),
        }
        df = pd.DataFrame(data, index=pd.date_range("2025-09-01", periods=n, freq="B"))
        return pd.concat({"Close": df}, axis=1)

    def test_returns_table_with_all_periods(self):
        mock_hist = self._mock_download()
        mock_info = {"sector": "Technology"}

        with patch("yfinance.Ticker") as mock_ticker, \
             patch("yfinance.download", return_value=mock_hist):
            mock_ticker.return_value.info = mock_info
            from tradingagents.dataflows.peer_comparison import get_sector_relative_report
            result = get_sector_relative_report("AAPL")

        for period in ["1-Week", "1-Month", "3-Month", "6-Month", "YTD"]:
            assert period in result

    def test_unknown_sector_returns_graceful_message(self):
        mock_info = {"sector": "UnknownSector"}
        with patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.info = mock_info
            from tradingagents.dataflows.peer_comparison import get_sector_relative_report
            result = get_sector_relative_report("XYZ")
        assert "No ETF benchmark" in result


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestPeerComparisonIntegration:
    def test_peer_comparison_tool(self):
        from tradingagents.agents.utils.fundamental_data_tools import get_peer_comparison
        result = get_peer_comparison.invoke({"ticker": "AAPL", "curr_date": "2026-03-17"})
        assert isinstance(result, str)
        assert len(result) > 50

    def test_sector_relative_tool(self):
        from tradingagents.agents.utils.fundamental_data_tools import get_sector_relative
        result = get_sector_relative.invoke({"ticker": "AAPL", "curr_date": "2026-03-17"})
        assert isinstance(result, str)
        assert len(result) > 50
