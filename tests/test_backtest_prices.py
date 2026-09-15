"""Tests for backtest price loading and the on-disk cache.

The cache is what makes ``--score-only`` free, so the round-trip through CSV is
tested directly rather than assumed.
"""

import pandas as pd
import pytest

from tradingagents.backtest.portfolio import simulate
from tradingagents.backtest.prices import (
    SETTLEMENT_BUFFER_DAYS,
    load_prices,
    normalize_index,
)


def frame(index):
    return pd.DataFrame(
        {"Open": [100.0] * len(index), "Close": [100.0] * len(index)}, index=index
    )


def dst_crossing_frame():
    """Bars either side of a US DST change, as yfinance returns them.

    March 6 is UTC-05:00 and March 12 is UTC-04:00, so a naive CSV round-trip
    produces mixed offsets that pandas cannot parse back into a DatetimeIndex.
    """
    index = pd.DatetimeIndex(
        pd.to_datetime(["2026-03-06", "2026-03-09", "2026-03-12"])
    ).tz_localize("America/New_York")
    return frame(index)


# ---------------------------------------------------------------------------
# normalize_index
# ---------------------------------------------------------------------------

def test_normalize_index_drops_the_timezone():
    normalized = normalize_index(dst_crossing_frame())

    assert isinstance(normalized.index, pd.DatetimeIndex)
    assert normalized.index.tz is None


def test_normalize_index_is_idempotent():
    once = normalize_index(dst_crossing_frame())
    twice = normalize_index(once)

    assert list(once.index) == list(twice.index)


def test_normalize_index_keeps_the_calendar_dates():
    normalized = normalize_index(dst_crossing_frame())

    assert [d.strftime("%Y-%m-%d") for d in normalized.index] == [
        "2026-03-06", "2026-03-09", "2026-03-12",
    ]


# ---------------------------------------------------------------------------
# Cache round-trip
# ---------------------------------------------------------------------------

def test_cached_prices_survive_a_dst_crossing(tmp_path):
    """Regression: mixed UTC offsets used to come back as a string index.

    The first pass fetched fresh and worked; every later --score-only read the
    cache and failed in simulate with "prices must be indexed by a
    DatetimeIndex" — breaking the whole point of the store.
    """
    cache = tmp_path / "prices"
    fetcher = lambda *a: dst_crossing_frame()  # noqa: E731

    load_prices(["NVDA"], "2026-03-01", "2026-03-15", cache_dir=cache, fetcher=fetcher)

    def explode(*a):
        raise AssertionError("should have been served from cache")

    cached = load_prices(
        ["NVDA"], "2026-03-01", "2026-03-15", cache_dir=cache, fetcher=explode
    )

    assert isinstance(cached["NVDA"].index, pd.DatetimeIndex)
    # And the cached frame is actually usable for scoring.
    result = simulate([("2026-03-06", "Buy")], cached["NVDA"])
    assert len(result.equity) == 3


def test_a_rescore_matches_the_first_pass(tmp_path):
    cache = tmp_path / "prices"
    fetcher = lambda *a: dst_crossing_frame()  # noqa: E731

    first = load_prices(["NVDA"], "2026-03-01", "2026-03-15",
                        cache_dir=cache, fetcher=fetcher)
    second = load_prices(["NVDA"], "2026-03-01", "2026-03-15",
                         cache_dir=cache, fetcher=fetcher)

    pd.testing.assert_frame_equal(first["NVDA"], second["NVDA"])


def test_tz_naive_prices_round_trip_too(tmp_path):
    cache = tmp_path / "prices"
    naive = frame(pd.bdate_range("2026-01-05", periods=5))

    load_prices(["NVDA"], "2026-01-05", "2026-01-09",
                cache_dir=cache, fetcher=lambda *a: naive)
    cached = load_prices(["NVDA"], "2026-01-05", "2026-01-09",
                         cache_dir=cache, fetcher=lambda *a: naive)

    assert isinstance(cached["NVDA"].index, pd.DatetimeIndex)


def test_an_unreadable_cache_falls_back_to_fetching(tmp_path):
    cache = tmp_path / "prices"
    cache.mkdir(parents=True)
    # Poison every cache file the loader might pick.
    for path in [cache / p for p in ("x.csv",)]:
        path.write_text("not,a,valid\ncsv", encoding="utf-8")

    calls = []

    def fetcher(ticker, start, end):
        calls.append(ticker)
        return frame(pd.bdate_range("2026-01-05", periods=3))

    prices = load_prices(["NVDA"], "2026-01-05", "2026-01-09",
                         cache_dir=cache, fetcher=fetcher)

    assert calls == ["NVDA"]
    assert isinstance(prices["NVDA"].index, pd.DatetimeIndex)


def test_a_corrupt_cache_file_is_refetched(tmp_path):
    cache = tmp_path / "prices"
    good = frame(pd.bdate_range("2026-01-05", periods=3))

    load_prices(["NVDA"], "2026-01-05", "2026-01-09",
                cache_dir=cache, fetcher=lambda *a: good)
    cached_file = next(cache.glob("*.csv"))
    cached_file.write_text("garbage\x00bytes", encoding="utf-8")

    calls = []

    def fetcher(ticker, start, end):
        calls.append(ticker)
        return good

    prices = load_prices(["NVDA"], "2026-01-05", "2026-01-09",
                         cache_dir=cache, fetcher=fetcher)

    assert calls == ["NVDA"]
    assert len(prices["NVDA"]) == 3


def test_loading_without_a_cache_dir_works(tmp_path):
    prices = load_prices(["NVDA"], "2026-01-05", "2026-01-09",
                         fetcher=lambda *a: frame(pd.bdate_range("2026-01-05", periods=3)))

    assert isinstance(prices["NVDA"].index, pd.DatetimeIndex)


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

def test_the_fetch_window_extends_past_the_last_decision():
    """Positions opened on the last decision still need bars to be marked."""
    captured = {}

    def fetcher(ticker, start, end):
        captured["end"] = end
        return frame(pd.bdate_range("2026-01-05", periods=3))

    load_prices(["NVDA"], "2026-01-05", "2026-02-05", fetcher=fetcher)

    expected = (
        pd.Timestamp("2026-02-05") + pd.Timedelta(days=SETTLEMENT_BUFFER_DAYS)
    ).strftime("%Y-%m-%d")
    assert captured["end"] == expected


@pytest.mark.parametrize("bad", [
    pd.DataFrame({"Open": [], "Close": []}, index=pd.DatetimeIndex([])),
    None,
])
def test_an_empty_fetch_is_omitted(tmp_path, bad):
    prices = load_prices(["NVDA"], "2026-01-05", "2026-01-09",
                         cache_dir=tmp_path / "p", fetcher=lambda *a: bad)

    assert prices == {}
