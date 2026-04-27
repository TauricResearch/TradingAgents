"""Integration tests for the Jintel vendor against live ``api.jintel.ai``.

Run with::

    pytest -m integration tests/test_jintel_integration.py

Skipped automatically when ``JINTEL_API_KEY`` is missing or set to the
``placeholder`` value the conftest fixture installs for unit tests.
"""

from __future__ import annotations

import os

import pytest

_KEY = os.environ.get("JINTEL_API_KEY", "")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _KEY or _KEY == "placeholder",
        reason="JINTEL_API_KEY not configured",
    ),
]

from tradingagents.dataflows import jintel as jmod  # noqa: E402
from tradingagents.dataflows.interface import route_to_vendor  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_caches():
    jmod._client = None
    jmod._fetch_financials_cached.cache_clear()
    yield


# ------------- the original 9 dispatched methods -------------

def test_get_stock_data():
    out = route_to_vendor("get_stock_data", "AAPL", "2025-10-01", "2025-10-15")
    assert out.startswith("Date,Open,High,Low,Close,Volume"), out[:80]


def test_get_indicators():
    out = route_to_vendor("get_indicators", "AAPL", "rsi", "2026-04-15", 30)
    assert any(c.isdigit() for c in out)


def test_get_fundamentals():
    out = route_to_vendor("get_fundamentals", "AAPL", "2026-04-15")
    assert "Fundamentals for AAPL" in out


def test_get_balance_sheet():
    out = route_to_vendor("get_balance_sheet", "AAPL", "annual", "2026-04-15")
    assert out.startswith("period_ending,total_assets"), out[:80]


def test_get_cashflow():
    out = route_to_vendor("get_cashflow", "AAPL", "annual", "2026-04-15")
    assert out.startswith("period_ending,operating_cash_flow"), out[:80]


def test_get_income_statement():
    out = route_to_vendor("get_income_statement", "AAPL", "annual", "2026-04-15")
    assert out.startswith("period_ending,total_revenue"), out[:80]


def test_get_news():
    """News in a date slice can legitimately be empty (sparse coverage / out
    of window). Either accept the empty string contract, or assert the header
    when content is present."""
    from datetime import datetime, timedelta
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    out = route_to_vendor("get_news", "AAPL", yesterday, today)
    if out:
        assert out.startswith("date,source,title,sentiment,link"), out[:80]


def test_get_global_news():
    """Same sparseness contract as test_get_news above."""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    out = route_to_vendor("get_global_news", today, 7, 5)
    if out:
        assert out.startswith("date,source,title,sentiment,link"), out[:80]


def test_get_insider_transactions():
    out = route_to_vendor("get_insider_transactions", "AAPL")
    assert "date,insider" in out


# ------------- Phase 4 (jintel-only) -------------

def test_get_filings():
    out = route_to_vendor("get_filings", "AAPL", "2026-04-15")
    assert out.startswith("form,filing_date,report_date,filing_url"), out[:80]


def test_get_macro_series_unrate():
    out = route_to_vendor("get_macro_series", "UNRATE", "2026-04-15", 365)
    assert out.startswith("date,value"), out[:80]


def test_get_top_holders_nvda():
    """AAPL has gaps in the 13F index; NVDA reliably populates."""
    out = route_to_vendor("get_top_holders", "NVDA")
    assert out.startswith("filer,cik,value"), out[:80]


# ------------- fallback behavior verified live -------------

def test_get_stock_data_intraday():
    """Hourly bars over the last week. Jintel's intraday window is ~1y."""
    from datetime import datetime, timedelta
    end = datetime.now().date()
    start = end - timedelta(days=7)
    out = route_to_vendor(
        "get_stock_data_intraday", "AAPL",
        start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"),
    )
    assert out.startswith("Date,Open,High,Low,Close,Volume"), out[:80]
    # Should have multiple hourly bars across 5 trading days
    assert len(out.splitlines()) > 5


def test_out_of_window_falls_to_yfinance():
    """OHLCV outside Jintel's index window must fall through to yfinance."""
    out = route_to_vendor("get_stock_data", "AAPL", "2010-01-04", "2010-01-29")
    # yfinance CSV uniquely includes the Dividends/Stock Splits columns
    assert "Dividends" in out or "Stock Splits" in out
