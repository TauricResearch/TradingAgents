"""The OHLCV cache: one file per symbol, fresh only on the day it was written.

A current-day request also refetches past a TTL, so a run started before the
day's bar was final is not served that snapshot all day (#1150). Keying the file
by symbol rather than by day keeps the cache from growing a file per symbol per
day (#1330).
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

from tradingagents.dataflows.vendors.yahoo import ohlcv

NOW = pd.Timestamp("2026-07-18 12:00")
STALE = ohlcv.OHLCV_CACHE_TTL_SECONDS + 60


def _stamp(path, ts):
    """Set ``path``'s mtime to the wall-clock ``ts``, read back in local time as
    the cache does. A naive ``pd.Timestamp.timestamp()`` would be taken as UTC."""
    t = ts.to_pydatetime().timestamp()
    os.utime(path, (t, t))


def _write(tmp_path, name="AAPL-YFin-data.csv", age_seconds=0.0, last_date="2026-07-17"):
    f = tmp_path / name
    pd.DataFrame({"Date": [last_date], "Close": [100.0]}).to_csv(f, index=False)
    _stamp(f, NOW - pd.Timedelta(seconds=age_seconds))
    return f


def _load(tmp_path, monkeypatch, curr_date, download):
    monkeypatch.setattr(ohlcv, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(ohlcv.pd.Timestamp, "today", staticmethod(lambda: NOW))
    monkeypatch.setattr(ohlcv.yf, "download", download)
    return ohlcv.load_ohlcv("AAPL", curr_date)


def _fail_download(*a, **k):
    raise AssertionError("fresh cache must not refetch")


@pytest.mark.unit
def test_current_day_cache_past_ttl_is_not_fresh(tmp_path):
    # Today's bar missing or still in progress: row inspection can't tell, so the TTL governs.
    assert ohlcv._cache_is_fresh(_write(tmp_path, age_seconds=STALE), NOW.normalize(), NOW) is False
    f = _write(tmp_path, age_seconds=STALE, last_date="2026-07-18")
    assert ohlcv._cache_is_fresh(f, NOW.normalize(), NOW) is False


@pytest.mark.unit
def test_recent_cache_is_fresh(tmp_path):
    # Written moments ago: don't hammer the vendor (weekend/holiday guard).
    assert ohlcv._cache_is_fresh(_write(tmp_path), NOW.normalize(), NOW) is True


@pytest.mark.unit
def test_historical_request_uses_todays_cache_past_the_ttl(tmp_path):
    f = _write(tmp_path, age_seconds=STALE, last_date="2026-04-30")
    assert ohlcv._cache_is_fresh(f, pd.Timestamp("2026-05-01"), NOW) is True


@pytest.mark.unit
def test_a_download_from_an_earlier_day_is_not_fresh(tmp_path):
    f = _write(tmp_path, age_seconds=13 * 3600)  # yesterday 23:00
    assert ohlcv._cache_is_fresh(f, pd.Timestamp("2026-05-01"), NOW) is False


@pytest.mark.unit
def test_load_ohlcv_refetches_stale_same_day_cache(tmp_path, monkeypatch):
    """End-to-end: the freshness check is wired into load_ohlcv's cache branch."""
    _write(tmp_path, age_seconds=STALE)
    calls = []

    def _fake_download(*a, **k):
        calls.append(1)
        return pd.DataFrame(
            {"Date": pd.to_datetime(["2026-07-17", "2026-07-18"]), "Close": [100.0, 222.0]}
        ).set_index("Date")

    out = _load(tmp_path, monkeypatch, "2026-07-18", _fake_download)
    assert calls, "stale same-day cache must trigger a refetch"
    assert 222.0 in out["Close"].values, "refreshed close must reach the caller"


@pytest.mark.unit
def test_load_ohlcv_reuses_fresh_same_day_cache(tmp_path, monkeypatch):
    _write(tmp_path, last_date="2026-07-18")
    _load(tmp_path, monkeypatch, "2026-07-18", _fail_download)


@pytest.mark.unit
def test_one_cache_file_per_symbol_across_days(tmp_path, monkeypatch):
    """A later day's download replaces the symbol's file instead of adding one (#1330)."""
    monkeypatch.setattr(ohlcv, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    frame = pd.DataFrame({"Date": pd.to_datetime(["2026-07-16", "2026-07-17"]), "Close": [1.0, 2.0]})
    downloads = []
    monkeypatch.setattr(ohlcv.yf, "download", lambda *a, **k: downloads.append(1) or frame.set_index("Date"))

    for day in ("2026-07-18 10:00", "2026-07-19 10:00", "2026-07-20 10:00"):
        now = pd.Timestamp(day)
        monkeypatch.setattr(ohlcv.pd.Timestamp, "today", staticmethod(lambda now=now: now))
        ohlcv.load_ohlcv("AAPL", "2026-07-17")
        written = list(tmp_path.glob("AAPL-*.csv"))
        _stamp(written[0], now)

    assert len(downloads) == 3, "each new day refetches"
    assert [p.name for p in tmp_path.iterdir()] == ["AAPL-YFin-data.csv"]
