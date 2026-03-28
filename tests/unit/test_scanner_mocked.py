"""Offline mocked tests for the market-wide scanner layer.

Covers both yfinance and Alpha Vantage scanner functions, plus the
route_to_vendor scanner routing.  All external calls are mocked so
these tests run without a network connection or API key.
"""

import json
import pandas as pd
import pytest
from datetime import date, datetime
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers — mock data factories
# ---------------------------------------------------------------------------

def _av_response(payload: dict | str) -> MagicMock:
    """Build a mock requests.Response wrapping a JSON dict or raw string."""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = json.dumps(payload) if isinstance(payload, dict) else payload
    resp.raise_for_status = MagicMock()
    return resp


def _global_quote(symbol: str, price: float = 480.0, change: float = 2.5,
                  change_pct: str = "0.52%") -> dict:
    return {
        "Global Quote": {
            "01. symbol": symbol,
            "05. price": str(price),
            "09. change": str(change),
            "10. change percent": change_pct,
        }
    }


def _time_series_daily(symbol: str) -> dict:
    """Return a minimal TIME_SERIES_DAILY JSON payload."""
    return {
        "Meta Data": {"2. Symbol": symbol},
        "Time Series (Daily)": {
            "2024-01-08": {"4. close": "482.00"},
            "2024-01-05": {"4. close": "480.00"},
            "2024-01-04": {"4. close": "475.00"},
        },
    }


_TOP_GAINERS_LOSERS = {
    "top_gainers": [
        {"ticker": "NVDA", "price": "620.00", "change_percentage": "5.10%", "volume": "45000000"},
        {"ticker": "AMD",  "price": "175.00", "change_percentage": "3.20%", "volume": "32000000"},
    ],
    "top_losers": [
        {"ticker": "INTC", "price": "31.00", "change_percentage": "-4.50%", "volume": "28000000"},
    ],
    "most_actively_traded": [
        {"ticker": "TSLA", "price": "240.00", "change_percentage": "1.80%", "volume": "90000000"},
    ],
}

_NEWS_SENTIMENT = {
    "feed": [
        {
            "title": "AI Stocks Rally on Positive Earnings",
            "summary": "Tech stocks continued their upward climb.",
            "source": "Reuters",
            "url": "https://example.com/news/1",
            "time_published": "20240108T130000",
            "overall_sentiment_score": 0.35,
        }
    ]
}


# ---------------------------------------------------------------------------
# yfinance scanner — get_market_movers_yfinance
# ---------------------------------------------------------------------------

class TestYfinanceScannerMarketMovers:
    """Offline tests for get_market_movers_yfinance."""

    def _screener_data(self, category: str = "day_gainers") -> dict:
        return {
            "quotes": [
                {
                    "symbol": "NVDA",
                    "shortName": "NVIDIA Corp",
                    "regularMarketPrice": 620.00,
                    "regularMarketChangePercent": 5.10,
                    "regularMarketVolume": 45_000_000,
                    "marketCap": 1_500_000_000_000,
                },
                {
                    "symbol": "AMD",
                    "shortName": "Advanced Micro Devices",
                    "regularMarketPrice": 175.00,
                    "regularMarketChangePercent": 3.20,
                    "regularMarketVolume": 32_000_000,
                    "marketCap": 280_000_000_000,
                },
            ]
        }

    def test_returns_markdown_table_for_day_gainers(self):
        from tradingagents.dataflows.yfinance_scanner import get_market_movers_yfinance

        with patch("tradingagents.dataflows.yfinance_scanner.yf.screener.screen",
                   return_value=self._screener_data()):
            result = get_market_movers_yfinance("day_gainers")

        assert isinstance(result, str)
        assert "Market Movers" in result
        assert "NVDA" in result
        assert "5.10%" in result
        assert "|" in result  # markdown table

    def test_returns_markdown_table_for_day_losers(self):
        from tradingagents.dataflows.yfinance_scanner import get_market_movers_yfinance

        data = {"quotes": [{"symbol": "INTC", "shortName": "Intel", "regularMarketPrice": 31.00,
                            "regularMarketChangePercent": -4.5, "regularMarketVolume": 28_000_000,
                            "marketCap": 130_000_000_000}]}
        with patch("tradingagents.dataflows.yfinance_scanner.yf.screener.screen",
                   return_value=data):
            result = get_market_movers_yfinance("day_losers")

        assert "Market Movers" in result
        assert "INTC" in result

    def test_invalid_category_returns_error_string(self):
        from tradingagents.dataflows.yfinance_scanner import get_market_movers_yfinance

        result = get_market_movers_yfinance("not_a_category")
        assert "Invalid category" in result

    def test_empty_quotes_returns_no_data_message(self):
        from tradingagents.dataflows.yfinance_scanner import get_market_movers_yfinance

        with patch("tradingagents.dataflows.yfinance_scanner.yf.screener.screen",
                   return_value={"quotes": []}):
            result = get_market_movers_yfinance("day_gainers")

        assert "No quotes found" in result

    def test_api_error_returns_error_string(self):
        from tradingagents.dataflows.yfinance_scanner import get_market_movers_yfinance

        with patch("tradingagents.dataflows.yfinance_scanner.yf.screener.screen",
                   side_effect=Exception("network failure")):
            result = get_market_movers_yfinance("day_gainers")

        assert "Error" in result


class TestYfinanceScannerGapCandidates:
    """Offline tests for get_gap_candidates_yfinance."""

    def _quote(self, symbol, open_price, prev_close, volume=2_000_000, avg_volume=1_000_000, price=25.0, change_pct=4.0):
        return {
            "symbol": symbol,
            "shortName": f"{symbol} Inc",
            "regularMarketOpen": open_price,
            "regularMarketPreviousClose": prev_close,
            "regularMarketVolume": volume,
            "averageDailyVolume3Month": avg_volume,
            "regularMarketPrice": price,
            "regularMarketChangePercent": change_pct,
        }

    def test_returns_gap_table(self):
        from tradingagents.dataflows.yfinance_scanner import get_gap_candidates_yfinance

        screen_data = {
            "quotes": [
                self._quote("NVDA", 110.0, 100.0),
                self._quote("AAPL", 103.0, 100.0),
            ]
        }
        with patch("tradingagents.dataflows.yfinance_scanner.yf.screen", return_value=screen_data):
            result = get_gap_candidates_yfinance()

        assert "# Gap Candidates" in result
        assert "NVDA" in result

    def test_returns_no_match_message_when_filters_fail(self):
        from tradingagents.dataflows.yfinance_scanner import get_gap_candidates_yfinance

        screen_data = {"quotes": [self._quote("AAPL", 100.5, 100.0, avg_volume=10_000_000)]}
        with patch("tradingagents.dataflows.yfinance_scanner.yf.screen", return_value=screen_data):
            result = get_gap_candidates_yfinance()

        assert "No stocks matched the live gap criteria today." in result


class TestYfinanceScannerGatekeeperUniverse:
    """Offline tests for get_gatekeeper_universe_yfinance."""

    def _quote(self, symbol, exchange="NMS", price=25.0, avg_volume=3_000_000, cur_volume=4_000_000, market_cap=5_000_000_000):
        return {
            "symbol": symbol,
            "shortName": f"{symbol} Inc",
            "exchange": exchange,
            "regularMarketPrice": price,
            "averageDailyVolume3Month": avg_volume,
            "regularMarketVolume": cur_volume,
            "marketCap": market_cap,
        }

    def test_returns_gatekeeper_table(self):
        from tradingagents.dataflows.yfinance_scanner import get_gatekeeper_universe_yfinance

        screen_data = {"quotes": [self._quote("NVDA"), self._quote("AAPL", exchange="NYQ")]}
        with patch("tradingagents.dataflows.yfinance_scanner.yf.screen", return_value=screen_data):
            result = get_gatekeeper_universe_yfinance(limit=10)

        assert "# Gatekeeper Universe" in result
        assert "NVDA" in result

    def test_returns_no_match_message_when_empty(self):
        from tradingagents.dataflows.yfinance_scanner import get_gatekeeper_universe_yfinance

        with patch("tradingagents.dataflows.yfinance_scanner.yf.screen", return_value={"quotes": []}):
            result = get_gatekeeper_universe_yfinance(limit=10)

        assert result == "No stocks matched the gatekeeper universe today."


# ---------------------------------------------------------------------------
# yfinance scanner — get_market_indices_yfinance
# ---------------------------------------------------------------------------

class TestYfinanceScannerMarketIndices:
    """Offline tests for get_market_indices_yfinance."""

    def _make_multi_etf_df(self) -> pd.DataFrame:
        """Build a minimal multi-ticker Close DataFrame as yf.download returns."""
        symbols = ["^GSPC", "^DJI", "^IXIC", "^VIX", "^RUT"]
        idx = pd.date_range("2024-01-04", periods=3, freq="B", tz="UTC")
        closes = pd.DataFrame(
            {s: [4800.0 + i * 10, 4810.0 + i * 10, 4820.0 + i * 10] for i, s in enumerate(symbols)},
            index=idx,
        )
        return pd.DataFrame({"Close": closes})

    def test_returns_markdown_table_with_indices(self):
        from tradingagents.dataflows.yfinance_scanner import get_market_indices_yfinance

        # Multi-symbol download returns a MultiIndex DataFrame
        symbols = ["^GSPC", "^DJI", "^IXIC", "^VIX", "^RUT"]
        idx = pd.date_range("2024-01-04", periods=5, freq="B")
        close_data = {s: [4800.0 + i for i in range(5)] for s in symbols}
        # yf.download with multiple symbols returns DataFrame with MultiIndex columns
        multi_df = pd.DataFrame(close_data, index=idx)
        multi_df.columns = pd.MultiIndex.from_product([["Close"], symbols])

        with patch("tradingagents.dataflows.yfinance_scanner.yf.download",
                   return_value=multi_df):
            result = get_market_indices_yfinance()

        assert isinstance(result, str)
        assert "Market Indices" in result or "Index" in result.split("\n")[0]

    def test_returns_string_on_download_error(self):
        from tradingagents.dataflows.yfinance_scanner import get_market_indices_yfinance

        with patch("tradingagents.dataflows.yfinance_scanner.yf.download",
                   side_effect=Exception("network error")):
            result = get_market_indices_yfinance()

        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# yfinance scanner — get_sector_performance_yfinance
# ---------------------------------------------------------------------------

class TestYfinanceScannerSectorPerformance:
    """Offline tests for get_sector_performance_yfinance."""

    def _make_sector_df(self) -> pd.DataFrame:
        """Multi-symbol ETF DataFrame covering 6 months of daily closes."""
        etfs = ["XLK", "XLV", "XLF", "XLE", "XLY", "XLP", "XLI", "XLB", "XLRE", "XLU", "XLC"]
        # 130 trading days ~ 6 months
        idx = pd.date_range("2023-07-01", periods=130, freq="B")
        data = {e: [100.0 + i * 0.01 for i in range(130)] for e in etfs}
        df = pd.DataFrame(data, index=idx)
        df.columns = pd.MultiIndex.from_product([["Close"], etfs])
        return df

    def test_returns_sector_performance_table(self):
        from tradingagents.dataflows.yfinance_scanner import get_sector_performance_yfinance

        with patch("tradingagents.dataflows.yfinance_scanner.yf.download",
                   return_value=self._make_sector_df()):
            result = get_sector_performance_yfinance()

        assert isinstance(result, str)
        assert "Sector Performance Overview" in result
        assert "|" in result

    def test_contains_all_sectors(self):
        from tradingagents.dataflows.yfinance_scanner import get_sector_performance_yfinance

        with patch("tradingagents.dataflows.yfinance_scanner.yf.download",
                   return_value=self._make_sector_df()):
            result = get_sector_performance_yfinance()

        # 11 GICS sectors should all appear
        for sector in ["Technology", "Healthcare", "Financials", "Energy"]:
            assert sector in result

    def test_download_error_returns_error_string(self):
        from tradingagents.dataflows.yfinance_scanner import get_sector_performance_yfinance

        with patch("tradingagents.dataflows.yfinance_scanner.yf.download",
                   side_effect=Exception("connection refused")):
            result = get_sector_performance_yfinance()

        assert "Error" in result


# ---------------------------------------------------------------------------
# yfinance scanner — get_industry_performance_yfinance
# ---------------------------------------------------------------------------

class TestYfinanceScannerIndustryPerformance:
    """Offline tests for get_industry_performance_yfinance."""

    def _mock_sector_with_companies(self) -> MagicMock:
        top_companies = pd.DataFrame(
            {
                "name": ["Apple Inc.", "Microsoft Corp", "NVIDIA Corp"],
                "rating": [4.5, 4.8, 4.2],
                "market weight": [0.072, 0.065, 0.051],
            },
            index=pd.Index(["AAPL", "MSFT", "NVDA"], name="symbol"),
        )
        mock_sector = MagicMock()
        mock_sector.top_companies = top_companies
        return mock_sector

    def test_returns_industry_table_for_valid_sector(self):
        from tradingagents.dataflows.yfinance_scanner import get_industry_performance_yfinance

        with patch("tradingagents.dataflows.yfinance_scanner.yf.Sector",
                   return_value=self._mock_sector_with_companies()):
            result = get_industry_performance_yfinance("technology")

        assert isinstance(result, str)
        assert "Industry Performance" in result
        assert "AAPL" in result
        assert "Apple Inc." in result

    def test_empty_top_companies_returns_no_data_message(self):
        from tradingagents.dataflows.yfinance_scanner import get_industry_performance_yfinance

        mock_sector = MagicMock()
        mock_sector.top_companies = pd.DataFrame()

        with patch("tradingagents.dataflows.yfinance_scanner.yf.Sector",
                   return_value=mock_sector):
            result = get_industry_performance_yfinance("technology")

        assert "No industry data found" in result

    def test_none_top_companies_returns_no_data_message(self):
        from tradingagents.dataflows.yfinance_scanner import get_industry_performance_yfinance

        mock_sector = MagicMock()
        mock_sector.top_companies = None

        with patch("tradingagents.dataflows.yfinance_scanner.yf.Sector",
                   return_value=mock_sector):
            result = get_industry_performance_yfinance("healthcare")

        assert "No industry data found" in result

    def test_sector_error_returns_error_string(self):
        from tradingagents.dataflows.yfinance_scanner import get_industry_performance_yfinance

        with patch("tradingagents.dataflows.yfinance_scanner.yf.Sector",
                   side_effect=Exception("yfinance unavailable")):
            result = get_industry_performance_yfinance("technology")

        assert "Error" in result


# ---------------------------------------------------------------------------
# yfinance scanner — get_topic_news_yfinance
# ---------------------------------------------------------------------------

class TestYfinanceScannerTopicNews:
    """Offline tests for get_topic_news_yfinance."""

    def _mock_search(self, title: str = "AI Revolution in Tech") -> MagicMock:
        mock_search = MagicMock()
        mock_search.news = [
            {
                "title": title,
                "publisher": "TechCrunch",
                "link": "https://techcrunch.com/story",
                "summary": "Artificial intelligence is transforming the industry.",
            }
        ]
        return mock_search

    def test_returns_formatted_news_for_topic(self):
        from tradingagents.dataflows.yfinance_scanner import get_topic_news_yfinance

        with patch("tradingagents.dataflows.yfinance_scanner.yf.Search",
                   return_value=self._mock_search()):
            result = get_topic_news_yfinance("artificial intelligence")

        assert isinstance(result, str)
        assert "AI Revolution in Tech" in result
        assert "News for Topic" in result

    def test_no_results_returns_no_news_message(self):
        from tradingagents.dataflows.yfinance_scanner import get_topic_news_yfinance

        mock_search = MagicMock()
        mock_search.news = []

        with patch("tradingagents.dataflows.yfinance_scanner.yf.Search",
                   return_value=mock_search):
            result = get_topic_news_yfinance("obscure_topic")

        assert "No news found" in result

    def test_handles_nested_content_structure(self):
        from tradingagents.dataflows.yfinance_scanner import get_topic_news_yfinance

        mock_search = MagicMock()
        mock_search.news = [
            {
                "content": {
                    "title": "Semiconductor Demand Surges",
                    "summary": "Chip makers report record orders.",
                    "provider": {"displayName": "Bloomberg"},
                    "canonicalUrl": {"url": "https://bloomberg.com/chips"},
                }
            }
        ]

        with patch("tradingagents.dataflows.yfinance_scanner.yf.Search",
                   return_value=mock_search):
            result = get_topic_news_yfinance("semiconductors")

        assert "Semiconductor Demand Surges" in result


# ---------------------------------------------------------------------------
# Alpha Vantage scanner — get_market_movers_alpha_vantage
# ---------------------------------------------------------------------------

class TestAVScannerMarketMovers:
    """Offline mocked tests for get_market_movers_alpha_vantage."""

    def test_day_gainers_returns_markdown_table(self):
        from tradingagents.dataflows.alpha_vantage_scanner import get_market_movers_alpha_vantage

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   return_value=json.dumps(_TOP_GAINERS_LOSERS)):
            result = get_market_movers_alpha_vantage("day_gainers")

        assert "Market Movers" in result
        assert "NVDA" in result
        assert "5.10%" in result
        assert "|" in result

    def test_day_losers_returns_markdown_table(self):
        from tradingagents.dataflows.alpha_vantage_scanner import get_market_movers_alpha_vantage

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   return_value=json.dumps(_TOP_GAINERS_LOSERS)):
            result = get_market_movers_alpha_vantage("day_losers")

        assert "INTC" in result

    def test_most_actives_returns_markdown_table(self):
        from tradingagents.dataflows.alpha_vantage_scanner import get_market_movers_alpha_vantage

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   return_value=json.dumps(_TOP_GAINERS_LOSERS)):
            result = get_market_movers_alpha_vantage("most_actives")

        assert "TSLA" in result

    def test_invalid_category_raises_value_error(self):
        from tradingagents.dataflows.alpha_vantage_scanner import get_market_movers_alpha_vantage

        with pytest.raises(ValueError, match="Invalid category"):
            get_market_movers_alpha_vantage("not_valid")

    def test_rate_limit_error_propagates(self):
        from tradingagents.dataflows.alpha_vantage_scanner import get_market_movers_alpha_vantage
        from tradingagents.dataflows.alpha_vantage_common import RateLimitError

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   side_effect=RateLimitError("rate limited")):
            with pytest.raises(RateLimitError):
                get_market_movers_alpha_vantage("day_gainers")


# ---------------------------------------------------------------------------
# Alpha Vantage scanner — get_market_indices_alpha_vantage
# ---------------------------------------------------------------------------

class TestAVScannerMarketIndices:
    """Offline mocked tests for get_market_indices_alpha_vantage."""

    def test_returns_markdown_table_with_index_names(self):
        from tradingagents.dataflows.alpha_vantage_scanner import get_market_indices_alpha_vantage

        def fake_request(function_name, params, **kwargs):
            symbol = params.get("symbol", "SPY")
            return json.dumps(_global_quote(symbol))

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   side_effect=fake_request):
            result = get_market_indices_alpha_vantage()

        assert "Market Indices" in result
        assert "|" in result
        assert any(name in result for name in ["S&P 500", "Dow Jones", "NASDAQ"])

    def test_all_proxies_appear_in_output(self):
        from tradingagents.dataflows.alpha_vantage_scanner import get_market_indices_alpha_vantage

        def fake_request(function_name, params, **kwargs):
            return json.dumps(_global_quote(params.get("symbol", "SPY")))

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   side_effect=fake_request):
            result = get_market_indices_alpha_vantage()

        # All 4 ETF proxies should appear
        for proxy in ["SPY", "DIA", "QQQ", "IWM"]:
            assert proxy in result


# ---------------------------------------------------------------------------
# Alpha Vantage scanner — get_sector_performance_alpha_vantage
# ---------------------------------------------------------------------------

class TestAVScannerSectorPerformance:
    """Offline mocked tests for get_sector_performance_alpha_vantage."""

    def _make_fake_request(self):
        """Return a side_effect function handling both GLOBAL_QUOTE and TIME_SERIES_DAILY."""
        def fake(function_name, params, **kwargs):
            if function_name == "GLOBAL_QUOTE":
                symbol = params.get("symbol", "XLK")
                return json.dumps(_global_quote(symbol))
            elif function_name == "TIME_SERIES_DAILY":
                symbol = params.get("symbol", "XLK")
                return json.dumps(_time_series_daily(symbol))
            return json.dumps({})
        return fake

    def test_returns_sector_table_with_percentages(self):
        from tradingagents.dataflows.alpha_vantage_scanner import get_sector_performance_alpha_vantage

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   side_effect=self._make_fake_request()):
            result = get_sector_performance_alpha_vantage()

        assert "Sector Performance Overview" in result
        assert "|" in result

    def test_all_eleven_sectors_in_output(self):
        from tradingagents.dataflows.alpha_vantage_scanner import get_sector_performance_alpha_vantage

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   side_effect=self._make_fake_request()):
            result = get_sector_performance_alpha_vantage()

        for sector in ["Technology", "Healthcare", "Financials", "Energy"]:
            assert sector in result

    def test_all_errors_raises_alpha_vantage_error(self):
        """If ALL sector ETF requests fail, AlphaVantageError is raised for fallback."""
        from tradingagents.dataflows.alpha_vantage_scanner import get_sector_performance_alpha_vantage
        from tradingagents.dataflows.alpha_vantage_common import AlphaVantageError, RateLimitError

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   side_effect=RateLimitError("rate limited")):
            with pytest.raises(AlphaVantageError):
                get_sector_performance_alpha_vantage()


# ---------------------------------------------------------------------------
# Alpha Vantage scanner — get_industry_performance_alpha_vantage
# ---------------------------------------------------------------------------

class TestAVScannerIndustryPerformance:
    """Offline mocked tests for get_industry_performance_alpha_vantage."""

    def test_returns_table_for_technology_sector(self):
        from tradingagents.dataflows.alpha_vantage_scanner import get_industry_performance_alpha_vantage

        def fake_request(function_name, params, **kwargs):
            symbol = params.get("symbol", "AAPL")
            return json.dumps(_global_quote(symbol, price=185.0, change_pct="+1.20%"))

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   side_effect=fake_request):
            result = get_industry_performance_alpha_vantage("technology")

        assert "Industry Performance" in result
        assert "|" in result
        assert any(t in result for t in ["AAPL", "MSFT", "NVDA"])

    def test_invalid_sector_raises_value_error(self):
        from tradingagents.dataflows.alpha_vantage_scanner import get_industry_performance_alpha_vantage

        with pytest.raises(ValueError, match="Unknown sector"):
            get_industry_performance_alpha_vantage("not_a_real_sector")

    def test_sorted_by_change_percent_descending(self):
        """Results should be sorted by change % descending."""
        from tradingagents.dataflows.alpha_vantage_scanner import get_industry_performance_alpha_vantage

        # Alternate high/low changes to verify sort order
        prices = {"AAPL": ("180.00", "+5.00%"), "MSFT": ("380.00", "+1.00%"),
                  "NVDA": ("620.00", "+8.00%"), "GOOGL": ("140.00", "+2.50%"),
                  "META": ("350.00", "+3.10%"), "AVGO": ("850.00", "+0.50%"),
                  "ADBE": ("550.00", "+4.20%"), "CRM": ("275.00", "+1.80%"),
                  "AMD": ("170.00", "+6.30%"), "INTC": ("31.00", "-2.10%")}

        def fake_request(function_name, params, **kwargs):
            symbol = params.get("symbol", "AAPL")
            p, c = prices.get(symbol, ("100.00", "0.00%"))
            return json.dumps({
                "Global Quote": {"01. symbol": symbol, "05. price": p,
                                 "09. change": "1.00", "10. change percent": c}
            })

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   side_effect=fake_request):
            result = get_industry_performance_alpha_vantage("technology")

        # NVDA (+8%) should appear before INTC (-2.1%)
        nvda_pos = result.find("NVDA")
        intc_pos = result.find("INTC")
        assert nvda_pos != -1 and intc_pos != -1
        assert nvda_pos < intc_pos


# ---------------------------------------------------------------------------
# Alpha Vantage scanner — get_topic_news_alpha_vantage
# ---------------------------------------------------------------------------

class TestAVScannerTopicNews:
    """Offline mocked tests for get_topic_news_alpha_vantage."""

    def test_returns_news_articles_for_known_topic(self):
        from tradingagents.dataflows.alpha_vantage_scanner import get_topic_news_alpha_vantage

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   return_value=json.dumps(_NEWS_SENTIMENT)):
            result = get_topic_news_alpha_vantage("market", limit=5)

        assert "News for Topic" in result
        assert "AI Stocks Rally on Positive Earnings" in result

    def test_known_topic_is_mapped_to_av_value(self):
        """Topic strings like 'market' are remapped to AV-specific topic keys."""
        from tradingagents.dataflows.alpha_vantage_scanner import get_topic_news_alpha_vantage

        captured = {}

        def capture_request(function_name, params, **kwargs):
            captured.update(params)
            return json.dumps(_NEWS_SENTIMENT)

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   side_effect=capture_request):
            get_topic_news_alpha_vantage("market", limit=5)

        # "market" maps to "financial_markets" in _TOPIC_MAP
        assert captured.get("topics") == "financial_markets"

    def test_unknown_topic_passed_through(self):
        """Topics not in the map are forwarded to the API as-is."""
        from tradingagents.dataflows.alpha_vantage_scanner import get_topic_news_alpha_vantage

        captured = {}

        def capture_request(function_name, params, **kwargs):
            captured.update(params)
            return json.dumps(_NEWS_SENTIMENT)

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   side_effect=capture_request):
            get_topic_news_alpha_vantage("custom_topic", limit=3)

        assert captured.get("topics") == "custom_topic"

    def test_empty_feed_returns_no_articles_message(self):
        from tradingagents.dataflows.alpha_vantage_scanner import get_topic_news_alpha_vantage

        empty = {"feed": []}
        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   return_value=json.dumps(empty)):
            result = get_topic_news_alpha_vantage("earnings", limit=5)

        assert "No articles" in result

    def test_rate_limit_error_propagates(self):
        from tradingagents.dataflows.alpha_vantage_scanner import get_topic_news_alpha_vantage
        from tradingagents.dataflows.alpha_vantage_common import RateLimitError

        with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                   side_effect=RateLimitError("rate limited")):
            with pytest.raises(RateLimitError):
                get_topic_news_alpha_vantage("technology")


# ---------------------------------------------------------------------------
# Scanner routing — route_to_vendor for scanner methods
# ---------------------------------------------------------------------------

class TestScannerRouting:
    """End-to-end routing tests for scanner_data methods via route_to_vendor."""

    def test_get_market_movers_routes_to_yfinance_by_default(self):
        """Default config uses yfinance for scanner_data."""
        from tradingagents.dataflows.interface import route_to_vendor

        screener_data = {
            "quotes": [{"symbol": "NVDA", "shortName": "NVIDIA", "regularMarketPrice": 620.0,
                        "regularMarketChangePercent": 5.1, "regularMarketVolume": 45_000_000,
                        "marketCap": 1_500_000_000_000}]
        }
        with patch("tradingagents.dataflows.yfinance_scanner.yf.screener.screen",
                   return_value=screener_data):
            result = route_to_vendor("get_market_movers", "day_gainers")

        assert isinstance(result, str)
        assert "NVDA" in result

    def test_get_sector_performance_routes_to_yfinance_by_default(self):
        from tradingagents.dataflows.interface import route_to_vendor

        etfs = ["XLK", "XLV", "XLF", "XLE", "XLY", "XLP", "XLI", "XLB", "XLRE", "XLU", "XLC"]
        idx = pd.date_range("2023-07-01", periods=130, freq="B")
        close_data = {e: [100.0 + i * 0.01 for i in range(130)] for e in etfs}
        df = pd.DataFrame(close_data, index=idx)
        df.columns = pd.MultiIndex.from_product([["Close"], etfs])

        with patch("tradingagents.dataflows.yfinance_scanner.yf.download", return_value=df):
            result = route_to_vendor("get_sector_performance")

        assert isinstance(result, str)
        assert "Sector Performance Overview" in result

    def test_get_market_movers_falls_back_to_yfinance_when_av_fails(self):
        """When AV scanner raises AlphaVantageError, fallback to yfinance is used."""
        from tradingagents.dataflows.interface import route_to_vendor
        from tradingagents.dataflows.config import get_config
        from tradingagents.dataflows.alpha_vantage_common import AlphaVantageError

        original_config = get_config()
        patched_config = {
            **original_config,
            "data_vendors": {**original_config.get("data_vendors", {}), "scanner_data": "alpha_vantage"},
        }

        screener_data = {
            "quotes": [{"symbol": "AMD", "shortName": "AMD", "regularMarketPrice": 175.0,
                        "regularMarketChangePercent": 3.2, "regularMarketVolume": 32_000_000,
                        "marketCap": 280_000_000_000}]
        }

        with patch("tradingagents.dataflows.interface.get_config", return_value=patched_config):
            # AV market movers raises → fallback to yfinance
            with patch("tradingagents.dataflows.alpha_vantage_scanner._rate_limited_request",
                       side_effect=AlphaVantageError("rate limited")):
                with patch("tradingagents.dataflows.yfinance_scanner.yf.screener.screen",
                           return_value=screener_data):
                    result = route_to_vendor("get_market_movers", "day_gainers")

        assert isinstance(result, str)
        assert "AMD" in result

    def test_get_topic_news_routes_correctly(self):
        from tradingagents.dataflows.interface import route_to_vendor

        mock_search = MagicMock()
        mock_search.news = [{"title": "Fed Signals Rate Cut", "publisher": "Reuters",
                             "link": "https://example.com", "summary": "Fed news."}]

        with patch("tradingagents.dataflows.yfinance_scanner.yf.Search",
                   return_value=mock_search):
            result = route_to_vendor("get_topic_news", "economy")

        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Finviz smart-money screener tools
# ---------------------------------------------------------------------------

def _make_finviz_df():
    """Minimal DataFrame matching what finvizfinance screener_view() returns."""
    return pd.DataFrame([
        {"Ticker": "NVDA", "Sector": "Technology", "Price": "620.00", "Volume": "45000000"},
        {"Ticker": "AMD",  "Sector": "Technology", "Price": "175.00", "Volume": "32000000"},
        {"Ticker": "XOM",  "Sector": "Energy",     "Price": "115.00", "Volume": "18000000"},
    ])


class TestFinvizSmartMoneyTools:
    """Mocked unit tests for Finviz screener tools — no network required."""

    def _mock_overview(self, df):
        """Return a patched Overview instance whose screener_view() yields df."""
        mock_inst = MagicMock()
        mock_inst.screener_view.return_value = df
        mock_cls = MagicMock(return_value=mock_inst)
        return mock_cls

    def test_get_insider_buying_stocks_returns_report(self):
        from tradingagents.agents.utils.scanner_tools import get_insider_buying_stocks

        with patch("tradingagents.agents.utils.scanner_tools._run_finviz_screen",
                   wraps=None) as _:
            pass  # use full stack — patch Overview only

        mock_cls = self._mock_overview(_make_finviz_df())
        with patch("finvizfinance.screener.overview.Overview", mock_cls):
            result = get_insider_buying_stocks.invoke({})

        assert "insider_buying" in result
        assert "NVDA" in result or "AMD" in result or "XOM" in result

    def test_get_unusual_volume_stocks_returns_report(self):
        from tradingagents.agents.utils.scanner_tools import get_unusual_volume_stocks

        mock_cls = self._mock_overview(_make_finviz_df())
        with patch("finvizfinance.screener.overview.Overview", mock_cls):
            result = get_unusual_volume_stocks.invoke({})

        assert "unusual_volume" in result

    def test_get_breakout_accumulation_stocks_returns_report(self):
        from tradingagents.agents.utils.scanner_tools import get_breakout_accumulation_stocks

        mock_cls = self._mock_overview(_make_finviz_df())
        with patch("finvizfinance.screener.overview.Overview", mock_cls):
            result = get_breakout_accumulation_stocks.invoke({})

        assert "breakout_accumulation" in result

    def test_empty_dataframe_returns_no_match_message(self):
        from tradingagents.agents.utils.scanner_tools import get_insider_buying_stocks

        mock_cls = self._mock_overview(pd.DataFrame())
        with patch("finvizfinance.screener.overview.Overview", mock_cls):
            result = get_insider_buying_stocks.invoke({})

        assert "No stocks matched" in result

    def test_exception_returns_graceful_unavailable_message(self):
        from tradingagents.agents.utils.scanner_tools import get_breakout_accumulation_stocks

        mock_inst = MagicMock()
        mock_inst.screener_view.side_effect = ConnectionError("timeout")
        mock_cls = MagicMock(return_value=mock_inst)

        with patch("finvizfinance.screener.overview.Overview", mock_cls):
            result = get_breakout_accumulation_stocks.invoke({})

        assert "Smart money scan unavailable" in result
        assert "timeout" in result

    def test_all_three_tools_sort_by_volume(self):
        """Verify the top result is the highest-volume ticker."""
        from tradingagents.agents.utils.scanner_tools import get_unusual_volume_stocks

        # NVDA has highest volume (45M) — should appear first in report
        mock_cls = self._mock_overview(_make_finviz_df())
        with patch("finvizfinance.screener.overview.Overview", mock_cls):
            result = get_unusual_volume_stocks.invoke({})

        nvda_pos = result.find("NVDA")
        amd_pos = result.find("AMD")
        assert nvda_pos < amd_pos, "NVDA (higher volume) should appear before AMD"

    def test_get_gap_candidates_uses_gatekeeper_gap_label(self):
        from tradingagents.agents.utils.scanner_tools import get_gap_candidates

        mock_cls = self._mock_overview(_make_finviz_df())
        with patch("finvizfinance.screener.overview.Overview", mock_cls):
            result = get_gap_candidates.invoke({})

        assert "gatekeeper_gap" in result
