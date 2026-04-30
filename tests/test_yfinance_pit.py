"""Point-in-time correctness tests for yfinance fundamentals.

yfinance's ``Ticker.info`` always returns *live* snapshot values (current
market cap, TTM ratios, 52-week ranges) regardless of any historical date
supplied by the caller. ``get_fundamentals`` therefore reconstructs those
fields point-in-time from historical statements + price bars when
``curr_date`` is in the past, and preserves the prior behaviour for live
(None / today) calls.

These tests mock ``yfinance.Ticker`` so they do not hit the network.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows import y_finance


# A representative subset of the live-snapshot field labels the function
# is expected to *suppress* on historical calls. (Picked to span price-
# derived, TTM, and rolling-window categories.)
_LIVE_FIELD_LABELS = (
    "Market Cap",
    "PE Ratio (TTM)",
    "Forward PE",
    "Price to Book",
    "52 Week High",
    "50 Day Average",
    "200 Day Average",
    "Dividend Yield",
    "Revenue (TTM)",
    "EBITDA",
    "Free Cash Flow",
    "EPS (TTM)",
)

_STABLE_FIELD_LABELS = ("Name", "Sector", "Industry", "Beta")


def _fake_info():
    """Realistic-shaped yfinance Ticker.info payload (NVDA-like, April 2026)."""
    return {
        "longName": "NVIDIA Corporation",
        "sector": "Technology",
        "industry": "Semiconductors",
        "marketCap": 5_090_000_000_000,
        "trailingPE": 45.6,
        "forwardPE": 18.6,
        "pegRatio": 1.2,
        "priceToBook": 38.0,
        "trailingEps": 4.90,
        "forwardEps": 11.24,
        "dividendYield": 0.0002,
        "beta": 2.34,
        "fiftyTwoWeekHigh": 216.83,
        "fiftyTwoWeekLow": 104.08,
        "fiftyDayAverage": 186.23,
        "twoHundredDayAverage": 183.35,
        "totalRevenue": 215_940_000_000,
        "grossProfits": 156_000_000_000,
        "ebitda": 130_000_000_000,
        "netIncomeToCommon": 90_000_000_000,
        "profitMargins": 0.42,
        "operatingMargins": 0.55,
        "returnOnEquity": 0.95,
        "returnOnAssets": 0.45,
        "debtToEquity": 22.0,
        "currentRatio": 4.5,
        "bookValue": 2.5,
        "freeCashflow": 58_100_000_000,
    }


def _patch_ticker(info, **statement_overrides):
    """Patch yf.Ticker so that ``.info`` returns ``info`` and yf_retry passes through.

    Optional ``statement_overrides`` lets tests inject:
        history=DataFrame, quarterly_income_stmt=DataFrame,
        quarterly_balance_sheet=DataFrame, quarterly_cashflow=DataFrame,
        get_shares_full=Series, dividends=Series.
    Anything not passed is left as a default MagicMock attribute so the
    derivation module's ``_safe_attr`` / ``_safe_call`` swallow it cleanly.
    """
    fake_ticker = MagicMock()
    fake_ticker.info = info

    if "history" in statement_overrides:
        fake_ticker.history.return_value = statement_overrides["history"]
    if "get_shares_full" in statement_overrides:
        fake_ticker.get_shares_full.return_value = statement_overrides["get_shares_full"]
    for attr in (
        "quarterly_income_stmt",
        "quarterly_balance_sheet",
        "quarterly_cashflow",
        "dividends",
    ):
        if attr in statement_overrides:
            setattr(fake_ticker, attr, statement_overrides[attr])

    return patch.object(y_finance.yf, "Ticker", return_value=fake_ticker)


def _fake_history_2024():
    """One trading year of synthetic NVDA-like daily bars ending 2024-05-10."""
    end = pd.Timestamp("2024-05-10")
    idx = pd.bdate_range(end=end, periods=260)
    n = len(idx)
    closes = pd.Series(
        [40 + (i / n) * 50 for i in range(n)],
        index=idx,
    )
    return pd.DataFrame({
        "Open":   closes - 0.5,
        "High":   closes + 1.0,
        "Low":    closes - 1.0,
        "Close":  closes,
        "Volume": [50_000_000] * n,
    })


def _fake_income_stmt():
    """Quarterly income statement keyed on fiscal-period end dates ≤ 2024-05-10."""
    cols = [
        pd.Timestamp("2024-04-30"),  # Q1 FY25
        pd.Timestamp("2024-01-31"),  # Q4 FY24
        pd.Timestamp("2023-10-31"),  # Q3 FY24
        pd.Timestamp("2023-07-31"),  # Q2 FY24
        pd.Timestamp("2023-04-30"),  # extra older quarter
    ]
    return pd.DataFrame({
        cols[0]: [26_000_000_000, 18_000_000_000, 16_000_000_000, 14_500_000_000],
        cols[1]: [22_103_000_000, 16_791_000_000, 14_000_000_000, 12_840_000_000],
        cols[2]: [18_120_000_000, 13_400_000_000, 11_300_000_000, 10_417_000_000],
        cols[3]: [13_510_000_000,  9_462_000_000,  7_640_000_000,  6_188_000_000],
        cols[4]: [ 7_192_000_000,  4_648_000_000,  3_490_000_000,  2_043_000_000],
    }, index=["Total Revenue", "Gross Profit", "Operating Income", "Net Income"])


def _fake_balance_sheet():
    cols = [
        pd.Timestamp("2024-04-30"),
        pd.Timestamp("2024-01-31"),
        pd.Timestamp("2023-10-31"),
    ]
    return pd.DataFrame({
        cols[0]: [70_000_000_000, 50_000_000_000, 12_000_000_000, 30_000_000_000, 11_000_000_000],
        cols[1]: [65_700_000_000, 42_980_000_000,  9_700_000_000, 28_000_000_000,  9_500_000_000],
        cols[2]: [54_152_000_000, 36_500_000_000,  9_500_000_000, 23_000_000_000,  8_400_000_000],
    }, index=[
        "Total Assets",
        "Stockholders Equity",
        "Total Debt",
        "Current Assets",
        "Current Liabilities",
    ])


def _fake_cashflow():
    cols = [
        pd.Timestamp("2024-04-30"),
        pd.Timestamp("2024-01-31"),
        pd.Timestamp("2023-10-31"),
        pd.Timestamp("2023-07-31"),
    ]
    return pd.DataFrame({
        cols[0]: [14_000_000_000],
        cols[1]: [11_217_000_000],
        cols[2]: [ 7_040_000_000],
        cols[3]: [ 6_345_000_000],
    }, index=["Free Cash Flow"])


def _fake_shares_full():
    """Daily share-count series ending 2024-05-10."""
    end = pd.Timestamp("2024-05-10")
    idx = pd.bdate_range(end=end, periods=260)
    return pd.Series([2_460_000_000] * len(idx), index=idx)


def _fake_dividends_none():
    """NVDA-style: minimal/no dividends in window."""
    return pd.Series([], dtype=float)


def _full_pit_overrides():
    return dict(
        history=_fake_history_2024(),
        quarterly_income_stmt=_fake_income_stmt(),
        quarterly_balance_sheet=_fake_balance_sheet(),
        quarterly_cashflow=_fake_cashflow(),
        get_shares_full=_fake_shares_full(),
        dividends=_fake_dividends_none(),
    )


@pytest.mark.unit
def test_historical_curr_date_reconstructs_pit_snapshot():
    """A past curr_date must reconstruct snapshot fields from PIT data, NOT
    return the live ``info`` snapshot."""
    past = "2024-05-10"
    with _patch_ticker(_fake_info(), **_full_pit_overrides()):
        out = y_finance.get_fundamentals("NVDA", curr_date=past)

    assert "Market Cap:" in out, "Market Cap should be reconstructed for historical"
    # Reconstructed market cap must NOT match the poisoned live info value.
    # Live info has Market Cap = 5,090,000,000,000 (April 2026).
    # PIT-reconstructed = close × shares_out = ~89.5 × 2.46B ≈ ~220B (synthetic).
    assert "5090000000000" not in out
    assert "Revenue (TTM):" in out
    assert "EPS (TTM):" in out
    assert "PE Ratio (TTM):" in out

    for label in _STABLE_FIELD_LABELS:
        assert f"{label}:" in out, f"stable field {label!r} missing from output"

    assert "Point-in-time mode" in out
    assert past in out
    assert "reconstructed" in out
    assert "Forward EPS:" not in out
    assert "Forward PE:" not in out
    assert "PEG Ratio:" not in out


@pytest.mark.unit
def test_historical_uses_only_quarters_at_or_before_curr_date():
    """Reconstructed TTM Revenue must equal the sum of the 4 quarters ending
    on or before curr_date, never including any later filing."""
    from tradingagents.dataflows.yf_pit_derivations import derive_pit_fundamentals

    fake_ticker = MagicMock()
    fake_ticker.info = _fake_info()
    fake_ticker.history.return_value = _fake_history_2024()
    fake_ticker.quarterly_income_stmt = _fake_income_stmt()
    fake_ticker.quarterly_balance_sheet = _fake_balance_sheet()
    fake_ticker.quarterly_cashflow = _fake_cashflow()
    fake_ticker.get_shares_full.return_value = _fake_shares_full()
    fake_ticker.dividends = _fake_dividends_none()

    derived = derive_pit_fundamentals(fake_ticker, "2024-05-10")

    # Last 4 quarters ≤ 2024-05-10:
    # 2024-04-30: 26.0B, 2024-01-31: 22.103B, 2023-10-31: 18.120B, 2023-07-31: 13.510B
    expected_ttm_rev = 26_000_000_000 + 22_103_000_000 + 18_120_000_000 + 13_510_000_000
    assert derived["Revenue (TTM)"] == expected_ttm_rev

    # Quarter at 2023-04-30 (7.192B) MUST NOT be included even though it's in the data.
    assert 7_192_000_000 not in [v for v in derived.values() if isinstance(v, (int, float))]


@pytest.mark.unit
def test_historical_market_cap_uses_close_at_curr_date_not_live():
    """Reconstructed Market Cap must = close[curr_date] × shares_outstanding[curr_date],
    not the live info snapshot."""
    from tradingagents.dataflows.yf_pit_derivations import derive_pit_fundamentals

    fake_ticker = MagicMock()
    fake_ticker.info = _fake_info()
    history = _fake_history_2024()
    fake_ticker.history.return_value = history
    fake_ticker.quarterly_income_stmt = _fake_income_stmt()
    fake_ticker.quarterly_balance_sheet = _fake_balance_sheet()
    fake_ticker.quarterly_cashflow = _fake_cashflow()
    fake_ticker.get_shares_full.return_value = _fake_shares_full()
    fake_ticker.dividends = _fake_dividends_none()

    derived = derive_pit_fundamentals(fake_ticker, "2024-05-10")

    expected_close = float(history.loc[history.index <= pd.Timestamp("2024-05-10")]["Close"].iloc[-1])
    expected_shares = 2_460_000_000
    expected_mcap = int(round(expected_close * expected_shares))

    assert derived["Market Cap"] == expected_mcap
    assert derived["Market Cap"] != 5_090_000_000_000


@pytest.mark.unit
def test_historical_52_week_range_from_history_window():
    """52-week H/L must derive from the 365-day window ending at curr_date."""
    from tradingagents.dataflows.yf_pit_derivations import derive_pit_fundamentals

    fake_ticker = MagicMock()
    fake_ticker.info = _fake_info()
    h = _fake_history_2024()
    fake_ticker.history.return_value = h
    fake_ticker.quarterly_income_stmt = _fake_income_stmt()
    fake_ticker.quarterly_balance_sheet = _fake_balance_sheet()
    fake_ticker.quarterly_cashflow = _fake_cashflow()
    fake_ticker.get_shares_full.return_value = _fake_shares_full()
    fake_ticker.dividends = _fake_dividends_none()

    derived = derive_pit_fundamentals(fake_ticker, "2024-05-10")

    cutoff = pd.Timestamp("2024-05-10")
    window = h[(h.index <= cutoff) & (h.index >= cutoff - pd.Timedelta(days=365))]
    expected_high = round(float(window["High"].max()), 2)
    expected_low = round(float(window["Low"].min()), 2)

    assert derived["52 Week High"] == expected_high
    assert derived["52 Week Low"] == expected_low
    # Live info has 52 Week High = 216.83 (2026 figure). Synthetic 2024 series
    # tops out at ~91; the live value must NOT be reused.
    assert derived["52 Week High"] != 216.83


@pytest.mark.unit
def test_historical_sparse_quarters_omit_ttm_gracefully():
    """If fewer than 4 quarters are available ≤ curr_date, TTM fields are omitted
    rather than a partial sum being published as if it were full-year data."""
    from tradingagents.dataflows.yf_pit_derivations import derive_pit_fundamentals

    sparse_income = pd.DataFrame({
        pd.Timestamp("2024-04-30"): [26_000_000_000, 18_000_000_000, 16_000_000_000, 14_500_000_000],
        pd.Timestamp("2024-01-31"): [22_103_000_000, 16_791_000_000, 14_000_000_000, 12_840_000_000],
    }, index=["Total Revenue", "Gross Profit", "Operating Income", "Net Income"])

    fake_ticker = MagicMock()
    fake_ticker.info = _fake_info()
    fake_ticker.history.return_value = _fake_history_2024()
    fake_ticker.quarterly_income_stmt = sparse_income
    fake_ticker.quarterly_balance_sheet = _fake_balance_sheet()
    fake_ticker.quarterly_cashflow = _fake_cashflow()
    fake_ticker.get_shares_full.return_value = _fake_shares_full()
    fake_ticker.dividends = _fake_dividends_none()

    derived = derive_pit_fundamentals(fake_ticker, "2024-05-10")

    assert "Revenue (TTM)" not in derived
    assert "Net Income" not in derived
    assert "EPS (TTM)" not in derived
    assert "PE Ratio (TTM)" not in derived
    # But price-derived ranges and book value (single-period) should still come through.
    assert "52 Week High" in derived
    assert "Book Value" in derived


@pytest.mark.unit
def test_historical_dividend_yield_uses_ttm_dividends_in_window():
    """Dividend yield = sum of dividends paid in the trailing 365 days ÷ close at curr_date."""
    from tradingagents.dataflows.yf_pit_derivations import derive_pit_fundamentals

    div_dates = [
        pd.Timestamp("2024-03-15"),
        pd.Timestamp("2023-12-15"),
        pd.Timestamp("2023-09-15"),
        pd.Timestamp("2023-06-15"),
    ]
    dividends = pd.Series([0.50, 0.50, 0.50, 0.50], index=div_dates)

    fake_ticker = MagicMock()
    fake_ticker.info = _fake_info()
    h = _fake_history_2024()
    fake_ticker.history.return_value = h
    fake_ticker.quarterly_income_stmt = _fake_income_stmt()
    fake_ticker.quarterly_balance_sheet = _fake_balance_sheet()
    fake_ticker.quarterly_cashflow = _fake_cashflow()
    fake_ticker.get_shares_full.return_value = _fake_shares_full()
    fake_ticker.dividends = dividends

    derived = derive_pit_fundamentals(fake_ticker, "2024-05-10")

    expected_close = float(h.loc[h.index <= pd.Timestamp("2024-05-10")]["Close"].iloc[-1])
    expected_yield = round(2.00 / expected_close, 4)
    assert derived["Dividend Yield"] == expected_yield


@pytest.mark.unit
def test_historical_no_dividend_history_omits_yield():
    """A ticker with no dividends in the trailing window does not emit Dividend Yield."""
    from tradingagents.dataflows.yf_pit_derivations import derive_pit_fundamentals

    fake_ticker = MagicMock()
    fake_ticker.info = _fake_info()
    fake_ticker.history.return_value = _fake_history_2024()
    fake_ticker.quarterly_income_stmt = _fake_income_stmt()
    fake_ticker.quarterly_balance_sheet = _fake_balance_sheet()
    fake_ticker.quarterly_cashflow = _fake_cashflow()
    fake_ticker.get_shares_full.return_value = _fake_shares_full()
    fake_ticker.dividends = _fake_dividends_none()

    derived = derive_pit_fundamentals(fake_ticker, "2024-05-10")
    assert "Dividend Yield" not in derived


@pytest.mark.unit
def test_derivation_failure_does_not_crash_get_fundamentals():
    """If the derivation module raises mid-run, get_fundamentals must still return
    a valid (degraded) report with the stable structural fields."""
    fake_ticker = MagicMock()
    fake_ticker.info = _fake_info()

    fake_ticker.history.side_effect = RuntimeError("yfinance exploded")

    type(fake_ticker).quarterly_income_stmt = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("statements unavailable"))
    )
    type(fake_ticker).quarterly_balance_sheet = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("statements unavailable"))
    )
    type(fake_ticker).quarterly_cashflow = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("statements unavailable"))
    )
    fake_ticker.get_shares_full.side_effect = RuntimeError("shares unavailable")
    type(fake_ticker).dividends = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("dividends unavailable"))
    )

    with patch.object(y_finance.yf, "Ticker", return_value=fake_ticker):
        out = y_finance.get_fundamentals("NVDA", curr_date="2024-05-10")

    for label in _STABLE_FIELD_LABELS:
        assert f"{label}:" in out
    assert "Point-in-time mode" in out
    assert "Market Cap:" not in out


@pytest.mark.unit
def test_no_curr_date_preserves_live_snapshot_fields():
    """Backwards compatibility: curr_date=None returns the full live snapshot."""
    with _patch_ticker(_fake_info()):
        out = y_finance.get_fundamentals("NVDA", curr_date=None)

    for label in _LIVE_FIELD_LABELS + _STABLE_FIELD_LABELS:
        assert f"{label}:" in out, f"{label!r} missing from live (no-curr_date) output"

    assert "Point-in-time mode" not in out


@pytest.mark.unit
def test_today_preserves_live_snapshot_fields():
    """curr_date == today is a *live* call and must not trip the historical guard."""
    today = datetime.now().date().strftime("%Y-%m-%d")
    with _patch_ticker(_fake_info()):
        out = y_finance.get_fundamentals("NVDA", curr_date=today)

    assert "Market Cap:" in out
    assert "Point-in-time mode" not in out


@pytest.mark.unit
def test_future_curr_date_treated_as_live():
    """A curr_date in the future is degenerate — fall back to live snapshot rather
    than silently returning an empty 'point-in-time' view."""
    future = (datetime.now().date() + timedelta(days=30)).strftime("%Y-%m-%d")
    with _patch_ticker(_fake_info()):
        out = y_finance.get_fundamentals("NVDA", curr_date=future)

    assert "Market Cap:" in out
    assert "Point-in-time mode" not in out


@pytest.mark.unit
def test_malformed_curr_date_treated_as_live():
    """Invalid curr_date strings must not silently suppress fields — fall back to live."""
    with _patch_ticker(_fake_info()):
        out = y_finance.get_fundamentals("NVDA", curr_date="not-a-date")

    assert "Market Cap:" in out
    assert "Point-in-time mode" not in out


@pytest.mark.unit
def test_empty_info_payload():
    """A None / empty info dict still produces a clean error string, not a crash."""
    with _patch_ticker({}):
        out = y_finance.get_fundamentals("NVDA", curr_date="2024-05-10")

    assert "No fundamentals data found" in out
