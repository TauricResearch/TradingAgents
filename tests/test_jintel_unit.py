"""Unit tests for ``tradingagents/dataflows/jintel.py`` (mocked JintelClient)."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from jintel import Err, JintelError, Ok

from tradingagents.dataflows import jintel as jmod
from tradingagents.dataflows.jintel import (
    JintelNoDataError,
    JintelRateLimitError,
    _is_no_data,
    _is_rate_limit,
    _unwrap,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Each test gets a fresh client + cleared memoization cache."""
    jmod._client = None
    jmod._fetch_financials_cached.cache_clear()
    yield
    jmod._client = None
    jmod._fetch_financials_cached.cache_clear()


@pytest.fixture
def mock_client(monkeypatch):
    m = MagicMock()
    monkeypatch.setattr(jmod, "_client", m)
    return m


# ------------------------------------------------------------------
# helper functions
# ------------------------------------------------------------------

class TestUnwrap:
    def test_ok_returns_data(self):
        assert _unwrap(Ok(data="value"), "ctx") == "value"

    def test_err_rate_limit_raises(self):
        with pytest.raises(JintelRateLimitError):
            _unwrap(Err(error="429 rate limit exceeded"), "ctx")

    def test_err_no_data_raises(self):
        with pytest.raises(JintelNoDataError):
            _unwrap(Err(error="Entity not found: FOO"), "ctx")

    def test_err_other_raises_jintel_error(self):
        with pytest.raises(JintelError):
            _unwrap(Err(error="Server bug"), "ctx")


@pytest.mark.parametrize(
    "msg,expected",
    [
        ("429 too many requests", True),
        ("rate limit exceeded", True),
        ("Quota exceeded for the day", True),
        ("Entity not found", False),
        ("Internal server error", False),
    ],
)
def test_is_rate_limit(msg, expected):
    assert _is_rate_limit(msg) is expected


@pytest.mark.parametrize(
    "msg,expected",
    [
        ("Entity not found: FOO", True),
        ("no data for ticker", True),
        ("Unknown ticker XYZ", True),
        ("no coverage in this region", True),
        ("network timeout", False),
        ("rate limit exceeded", False),
    ],
)
def test_is_no_data(msg, expected):
    assert _is_no_data(msg) is expected


# ------------------------------------------------------------------
# _get_client
# ------------------------------------------------------------------

class TestGetClient:
    def test_missing_key_raises_no_data(self, monkeypatch):
        monkeypatch.delenv("JINTEL_API_KEY", raising=False)
        jmod._client = None
        with pytest.raises(JintelNoDataError):
            jmod._get_client()

    def test_with_key_creates_client(self, monkeypatch):
        monkeypatch.setenv("JINTEL_API_KEY", "k_test")
        jmod._client = None
        with patch("tradingagents.dataflows.jintel.JintelClient") as MockClient:
            jmod._get_client()
            MockClient.assert_called_once_with(api_key="k_test")

    def test_singleton_reused(self, monkeypatch):
        monkeypatch.setenv("JINTEL_API_KEY", "k_test")
        jmod._client = None
        with patch("tradingagents.dataflows.jintel.JintelClient") as MockClient:
            jmod._get_client()
            jmod._get_client()
            MockClient.assert_called_once()


# ------------------------------------------------------------------
# get_stock
# ------------------------------------------------------------------

def _price_point(date, o, h, lo, c, v):
    return MagicMock(date=date, open=o, high=h, low=lo, close=c, volume=v)


class TestGetStock:
    def test_returns_full_ohlcv_csv(self, mock_client):
        entity = MagicMock()
        entity.market.history = [
            _price_point("2025-10-01", 100.0, 105.0, 99.0, 104.0, 1_000_000),
            _price_point("2025-10-02", 104.0, 106.0, 103.0, 105.5, 900_000),
        ]
        mock_client.enrich_entity.return_value = Ok(data=entity)
        out = jmod.get_stock("AAPL", "2025-10-01", "2025-10-02")
        assert out.splitlines()[0] == "Date,Open,High,Low,Close,Volume"
        assert "2025-10-01" in out
        assert "2025-10-02" in out

    def test_empty_history_raises_no_data(self, mock_client):
        entity = MagicMock()
        entity.market.history = []
        mock_client.enrich_entity.return_value = Ok(data=entity)
        with pytest.raises(JintelNoDataError):
            jmod.get_stock("FOO", "2010-01-01", "2010-01-31")

    def test_missing_market_raises_no_data(self, mock_client):
        entity = MagicMock()
        entity.market = None
        mock_client.enrich_entity.return_value = Ok(data=entity)
        with pytest.raises(JintelNoDataError):
            jmod.get_stock("FOO", "2010-01-01", "2010-01-31")

    def test_rate_limit_propagates(self, mock_client):
        mock_client.enrich_entity.return_value = Err(error="429 rate limit")
        with pytest.raises(JintelRateLimitError):
            jmod.get_stock("AAPL", "2025-10-01", "2025-10-02")

    def test_arrayfilter_limit_passed(self, mock_client):
        """Verifies we override the default limit=20 to support full backtests."""
        entity = MagicMock()
        entity.market.history = [_price_point("2025-10-01", 1, 1, 1, 1, 1)]
        mock_client.enrich_entity.return_value = Ok(data=entity)
        jmod.get_stock("AAPL", "2025-01-01", "2025-12-31")
        kwargs = mock_client.enrich_entity.call_args.kwargs
        opts = kwargs["options"]
        assert opts.filter.limit == 10000


# ------------------------------------------------------------------
# get_indicator
# ------------------------------------------------------------------

class TestGetIndicator:
    def test_propagates_no_data_from_get_stock(self, mock_client):
        entity = MagicMock()
        entity.market.history = []
        mock_client.enrich_entity.return_value = Ok(data=entity)
        with pytest.raises(JintelNoDataError):
            jmod.get_indicator("AAPL", "rsi", "2026-04-15", 30)


# ------------------------------------------------------------------
# get_fundamentals  (no as_of -- live snapshot)
# ------------------------------------------------------------------

class TestGetFundamentals:
    def test_does_not_pass_as_of(self, mock_client):
        """MarketData.quote and Entity.fundamentals are PIT-unsupported."""
        entity = MagicMock()
        entity.market.quote.price = 271.06
        entity.market.quote.market_cap = 4_000_000_000_000
        entity.market.fundamentals.model_dump.return_value = {"pe_ratio": 34.5}
        entity.analyst.model_dump.return_value = {"recommendation": "buy"}
        mock_client.enrich_entity.return_value = Ok(data=entity)
        jmod.get_fundamentals("AAPL", "2026-04-15")
        kwargs = mock_client.enrich_entity.call_args.kwargs
        # options either is None or, if present, lacks as_of
        opts = kwargs.get("options")
        assert opts is None or getattr(opts, "as_of", None) is None

    def test_emits_text_report(self, mock_client):
        entity = MagicMock()
        entity.market.quote.price = 271.06
        entity.market.quote.market_cap = 4_000_000_000_000
        entity.market.fundamentals.model_dump.return_value = {"pe_ratio": 34.5}
        entity.analyst.model_dump.return_value = {"recommendation": "buy"}
        mock_client.enrich_entity.return_value = Ok(data=entity)
        out = jmod.get_fundamentals("AAPL", "2026-04-15")
        assert "Fundamentals for AAPL" in out
        assert "271.06" in out
        assert "pe_ratio" in out
        assert "analyst_recommendation" in out


# ------------------------------------------------------------------
# Financial statements + memoization
# ------------------------------------------------------------------

def _financials(bs=None, cf=None, inc=None):
    e = MagicMock()
    e.financials = MagicMock()
    e.financials.balance_sheet = bs or []
    e.financials.cash_flow = cf or []
    e.financials.income = inc or []
    return e


class TestFinancials:
    def test_three_statements_one_http_call(self, mock_client):
        mock_client.enrich_entity.return_value = Ok(data=_financials())
        jmod.get_balance_sheet("AAPL", "annual", "2026-04-15")
        jmod.get_cashflow("AAPL", "annual", "2026-04-15")
        jmod.get_income_statement("AAPL", "annual", "2026-04-15")
        assert mock_client.enrich_entity.call_count == 1

    def test_different_dates_separate_calls(self, mock_client):
        mock_client.enrich_entity.return_value = Ok(data=_financials())
        jmod.get_balance_sheet("AAPL", "annual", "2026-04-15")
        jmod.get_balance_sheet("AAPL", "annual", "2026-04-14")
        assert mock_client.enrich_entity.call_count == 2

    def test_different_tickers_separate_calls(self, mock_client):
        mock_client.enrich_entity.return_value = Ok(data=_financials())
        jmod.get_balance_sheet("AAPL", "annual", "2026-04-15")
        jmod.get_balance_sheet("NVDA", "annual", "2026-04-15")
        assert mock_client.enrich_entity.call_count == 2

    def test_no_financials_raises_no_data(self, mock_client):
        entity = MagicMock()
        entity.financials = None
        mock_client.enrich_entity.return_value = Ok(data=entity)
        with pytest.raises(JintelNoDataError):
            jmod.get_balance_sheet("FOO", "annual", "2026-04-15")

    def test_freq_logged_when_not_annual(self, mock_client, caplog):
        import logging
        mock_client.enrich_entity.return_value = Ok(data=_financials())
        with caplog.at_level(logging.INFO, logger="tradingagents.dataflows.jintel"):
            jmod.get_balance_sheet("AAPL", "quarterly", "2026-04-15")
        assert "freq='quarterly'" in caplog.text


# ------------------------------------------------------------------
# News + insider trades
# ------------------------------------------------------------------

class TestNews:
    def test_get_news_includes_sentiment(self, mock_client):
        entity = MagicMock()
        entity.news = [
            MagicMock(date="2026-04-25", source="bloomberg", title="X",
                      sentiment_score=0.5, link="https://x"),
        ]
        mock_client.enrich_entity.return_value = Ok(data=entity)
        out = jmod.get_news("AAPL", "2026-04-01", "2026-04-26")
        assert out.splitlines()[0] == "date,source,title,sentiment,link"

    def test_global_news_includes_sentiment_column(self, mock_client):
        """Regression test for the round-1 schema-mismatch fix."""
        entity = MagicMock()
        entity.news = [
            MagicMock(date="2026-04-25", source="x", title="t",
                      sentiment_score=0.1, link="https://x"),
        ]
        mock_client.batch_enrich.return_value = Ok(data=[entity])
        out = jmod.get_global_news("2026-04-26", 7, 5)
        assert "sentiment" in out.splitlines()[0]


# ------------------------------------------------------------------
# Phase 4
# ------------------------------------------------------------------

class TestPhase4Filings:
    def test_returns_csv_with_sec_url(self, mock_client):
        entity = MagicMock()
        entity.periodic_filings = [
            MagicMock(form="10-Q", filing_date="2026-01-30",
                      report_date="2025-12-27",
                      filing_url="https://sec.gov/x"),
        ]
        mock_client.enrich_entity.return_value = Ok(data=entity)
        out = jmod.get_filings("AAPL", "2026-04-15")
        assert "10-Q" in out
        assert "https://sec.gov/x" in out

    def test_empty_raises_no_data(self, mock_client):
        entity = MagicMock()
        entity.periodic_filings = []
        mock_client.enrich_entity.return_value = Ok(data=entity)
        with pytest.raises(JintelNoDataError):
            jmod.get_filings("FOO")


class TestPhase4MacroSeries:
    def test_returns_csv(self, mock_client):
        ms = MagicMock()
        ms.observations = [
            MagicMock(date="2025-01-01", value=4.0),
            MagicMock(date="2025-02-01", value=4.1),
        ]
        mock_client.macro_series.return_value = Ok(data=ms)
        out = jmod.get_macro_series("UNRATE", "2026-04-15", 365)
        assert out.splitlines()[0] == "date,value"
        assert "4.0" in out

    def test_empty_observations_raises(self, mock_client):
        ms = MagicMock()
        ms.observations = []
        mock_client.macro_series.return_value = Ok(data=ms)
        with pytest.raises(JintelNoDataError):
            jmod.get_macro_series("BOGUS", "2026-04-15", 365)


class TestPhase4TopHolders:
    def test_returns_csv(self, mock_client):
        entity = MagicMock()
        entity.top_holders = [
            MagicMock(filer_name="ACME", cik="1234567",
                      value=1_000_000.0, shares=10_000.0,
                      report_date="2025-12-31", filing_date="2026-02-14"),
        ]
        mock_client.enrich_entity.return_value = Ok(data=entity)
        out = jmod.get_top_holders("AAPL")
        assert out.splitlines()[0] == "filer,cik,value,shares,report_date,filing_date"
        assert "ACME" in out
        assert "1234567" in out

    def test_empty_raises(self, mock_client):
        entity = MagicMock()
        entity.top_holders = []
        mock_client.enrich_entity.return_value = Ok(data=entity)
        with pytest.raises(JintelNoDataError):
            jmod.get_top_holders("FOO")
