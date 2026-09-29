"""Historical fundamentals must not leak a live company profile (#1300).

Vendor "company overview" endpoints (yfinance ``Ticker.info``, Alpha Vantage
``OVERVIEW``) serve only present-day values: market cap, valuation multiples,
the 52-week range and TTM income all move with today's quote, and even name,
sector and industry shift when a company renames or is reclassified. None of it
carries a historical vintage, so emitting it into a run dated in the past puts
post-decision information into the analyst's context, in the same family as the
FRED (#1275), social (#1220) and memory (#1251) leaks.

Both vendors withhold on one shared rule (``date_window.withhold_live_profile``)
so switching ``fundamental_data`` between them cannot reintroduce the leak. The
statement tools stay point-in-time by filtering on ``curr_date``, and a live run
is unchanged. All API access is mocked.
"""
from __future__ import annotations

from unittest import mock

import pytest

from tradingagents.dataflows import date_window
from tradingagents.dataflows.vendors.alpha_vantage import fundamentals as av
from tradingagents.dataflows.vendors.yahoo import (
    fundamentals as yahoo_fundamentals,
    market as yahoo_market,
)

_TODAY = "2026-09-07"
_PAST = "2024-05-10"

# A profile payload mixing stable-looking identity fields with market-dependent ones.
_INFO = {
    "longName": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "marketCap": 3_500_000_000_000,
    "trailingPE": 34.2,
    "fiftyTwoWeekHigh": 260.1,
    "totalRevenue": 391_000_000_000,
}

# Values that must never reach a historical run.
_LEAKY = ("3500000000000", "34.2", "260.1", "391000000000",
          "Apple Inc.", "Technology", "Consumer Electronics")


def _yf(curr_date, info=_INFO, today=_TODAY):
    with mock.patch.object(date_window, "get_current_date", return_value=today), \
         mock.patch.object(yahoo_fundamentals, "yf_retry", lambda fn: info), \
         mock.patch.object(yahoo_market.yf, "Ticker"):
        return yahoo_fundamentals.get_fundamentals("AAPL", curr_date)


def _av(curr_date, today=_TODAY):
    """Alpha Vantage path; the API call is mocked so a leak would be visible."""
    with mock.patch.object(date_window, "get_current_date", return_value=today), \
         mock.patch.object(av, "_make_api_request",
                           return_value="MarketCapitalization: 3500000000000") as req:
        return av.get_fundamentals("AAPL", curr_date), req


@pytest.mark.unit
class TestYFinanceHistoricalRun:
    def test_no_profile_value_survives(self):
        out = _yf(_PAST)
        for leaked in _LEAKY:
            assert leaked not in out, f"leaked live-profile value {leaked!r}"

    def test_states_the_as_of_date_and_explains_itself(self):
        # The analyst must be told why the figures are absent, so it does not
        # read the gap as a real signal or fabricate around it.
        out = _yf(_PAST)
        assert f"Point-in-time as of: {_PAST}" in out
        assert "withheld" in out
        assert _PAST in out and _TODAY not in out

    def test_no_wall_clock_retrieval_stamp(self):
        # The old header stamped datetime.now(), which is what surfaced the leak.
        assert "Data retrieved on:" not in _yf(_PAST)

    def test_the_request_is_not_even_made(self):
        # The response would only be discarded; skipping it also avoids burning
        # vendor quota on a call whose result cannot be used.
        with mock.patch.object(date_window, "get_current_date", return_value=_TODAY), \
             mock.patch.object(yahoo_market.yf, "Ticker") as tk:
            yahoo_fundamentals.get_fundamentals("AAPL", _PAST)
        tk.assert_not_called()


@pytest.mark.unit
class TestAlphaVantageHistoricalRun:
    """The same rule must hold for the other fundamentals vendor, or switching
    data_vendors["fundamental_data"] would silently reintroduce the leak."""

    def test_overview_is_withheld(self):
        out, _ = _av(_PAST)
        assert "3500000000000" not in out
        assert "withheld" in out
        assert f"Point-in-time as of: {_PAST}" in out

    def test_the_api_call_is_not_made(self):
        _, req = _av(_PAST)
        req.assert_not_called()

    def test_live_run_still_calls_the_api(self):
        out, req = _av(_TODAY)
        req.assert_called_once()
        assert "3500000000000" in out


@pytest.mark.unit
class TestLiveRunUnchanged:
    def test_yfinance_current_date_returns_the_full_profile(self):
        out = _yf(_TODAY)
        for value in _LEAKY:
            assert value in out
        assert "withheld" not in out

    def test_yfinance_absent_curr_date_returns_the_full_profile(self):
        out = _yf(None)
        assert "Market Cap: 3500000000000" in out
        assert "withheld" not in out


@pytest.mark.unit
class TestNoUsableFieldsStillRaises:
    def test_stub_payload_raises_no_market_data(self):
        # yfinance returns {"trailingPegRatio": None} for unknown symbols; on a
        # live run that must stay a hard "no data", not a bare header.
        from tradingagents.dataflows.errors import NoMarketDataError

        with pytest.raises(NoMarketDataError):
            _yf(_TODAY, info={"trailingPegRatio": None})
