"""Same-day OHLCV cache must not serve a stale snapshot all day (#1150).

The cache file is keyed per day, so a run started before the day's bar was final
would be reused by every later run, feeding a stale close into technical
analysis. Two cases matter for a current-day request: the bar may be missing, or
present but still in progress (Yahoo publishes a partial daily candle intraday).
Refresh is bounded by a TTL so repeated runs cannot hammer the vendor.
"""
from __future__ import annotations

import os
import time

import pandas as pd
import pytest

import tradingagents.dataflows.stockstats_utils as su

TODAY = pd.Timestamp("2026-07-18")
STALE = su.OHLCV_CACHE_TTL_SECONDS + 60


def _write(tmp_path, name="cache.csv", age_seconds=0.0, last_date="2026-07-17"):
    f = tmp_path / name
    pd.DataFrame({"Date": [last_date], "Close": [1.0]}).to_csv(f, index=False)
    if age_seconds:
        old = time.time() - age_seconds
        os.utime(f, (old, old))
    return str(f)


@pytest.mark.unit
def test_current_day_cache_past_ttl_is_refreshed(tmp_path):
    # Bar missing (rows stop at yesterday) and file older than the TTL -> refetch.
    assert su._needs_same_day_refresh(_write(tmp_path, age_seconds=STALE), TODAY, TODAY) is True


@pytest.mark.unit
def test_partial_current_day_bar_is_still_refreshed(tmp_path):
    # Today's row is present but may be an in-progress candle whose Close is not
    # the closing price. Row inspection can't distinguish it, so the TTL governs.
    f = _write(tmp_path, age_seconds=STALE, last_date="2026-07-18")
    assert su._needs_same_day_refresh(f, TODAY, TODAY) is True


@pytest.mark.unit
def test_recent_cache_is_not_refetched(tmp_path):
    # Written moments ago: don't hammer the vendor (weekend/holiday guard).
    assert su._needs_same_day_refresh(_write(tmp_path), TODAY, TODAY) is False


@pytest.mark.unit
def test_historical_request_always_uses_cache(tmp_path):
    # Past dates are immutable: never refetch, however old the file is.
    past = pd.Timestamp("2026-05-01")
    f = _write(tmp_path, age_seconds=STALE, last_date="2026-04-30")
    assert su._needs_same_day_refresh(f, past, TODAY) is False


@pytest.mark.unit
def test_load_ohlcv_refetches_stale_same_day_cache(tmp_path, monkeypatch):
    """End-to-end: the helper is actually wired into load_ohlcv's cache branch.

    Without this, the unit tests above would still pass if the helper were never
    called from the real code path.
    """
    monkeypatch.setattr(su, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(su.pd.Timestamp, "today", staticmethod(lambda: TODAY))

    # Pre-seed the cache file load_ohlcv will look for, aged past the TTL.
    start = (TODAY - pd.DateOffset(years=5)).strftime("%Y-%m-%d")
    end = (TODAY + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    cache_file = tmp_path / f"AAPL-YFin-data-{start}-{end}.csv"
    pd.DataFrame({"Date": ["2026-07-17"], "Close": [100.0]}).to_csv(cache_file, index=False)
    old = time.time() - STALE
    os.utime(cache_file, (old, old))

    calls = []

    def _fake_download(*a, **k):
        calls.append(1)
        return pd.DataFrame(
            {"Date": pd.to_datetime(["2026-07-17", "2026-07-18"]), "Close": [100.0, 222.0]}
        ).set_index("Date")

    monkeypatch.setattr(su.yf, "download", _fake_download)

    out = su.load_ohlcv("AAPL", TODAY.strftime("%Y-%m-%d"))

    assert calls, "stale same-day cache must trigger a refetch"
    assert 222.0 in out["Close"].values, "refreshed close must reach the caller"


@pytest.mark.unit
def test_load_ohlcv_reuses_fresh_same_day_cache(tmp_path, monkeypatch):
    # Mirror image: a fresh cache must NOT trigger a download.
    monkeypatch.setattr(su, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(su.pd.Timestamp, "today", staticmethod(lambda: TODAY))

    start = (TODAY - pd.DateOffset(years=5)).strftime("%Y-%m-%d")
    end = (TODAY + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    cache_file = tmp_path / f"AAPL-YFin-data-{start}-{end}.csv"
    pd.DataFrame({"Date": ["2026-07-18"], "Close": [100.0]}).to_csv(cache_file, index=False)

    def _fail_download(*a, **k):
        raise AssertionError("fresh cache must not refetch")

    monkeypatch.setattr(su.yf, "download", _fail_download)
    su.load_ohlcv("AAPL", TODAY.strftime("%Y-%m-%d"))
