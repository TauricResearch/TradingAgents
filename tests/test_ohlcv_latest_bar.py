"""The latest trading day's bar must not silently vanish (#1201).

yfinance can return the newest in-range bar with a NaN close (an unsettled or
glitched session). The old path parsed dates without normalizing timezone and
dropped every NaN-close row before applying the curr_date cutoff, so the latest
bar disappeared and the previous trading day looked like the latest. Now dates
are normalized before the cutoff, so the frame ends at the last settled bar
instead of carrying a fabricated close.

Refusing the whole frame instead (the first attempt at #1201) reported a
tradable symbol as invalid or delisted (#1289), so only a range with no close
anywhere counts as no data and the staleness check judges the rest.
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors.yahoo import ohlcv


def _stamp(path, ts):
    """Set ``path``'s mtime to the wall-clock ``ts``, read back in local time as
    the cache does. A naive ``pd.Timestamp.timestamp()`` would be taken as UTC."""
    t = ts.to_pydatetime().timestamp()
    os.utime(path, (t, t))

# --- date normalization -----------------------------------------------------


@pytest.mark.unit
def test_normalize_dates_strips_tz_and_normalizes_to_midnight():
    aware = pd.Series(pd.to_datetime(
        ["2026-05-08 09:30:00-04:00", "2026-05-09 16:00:00-04:00"]
    ))
    out = ohlcv._normalize_dates(aware)
    assert out.dt.tz is None
    assert list(out) == [pd.Timestamp("2026-05-08"), pd.Timestamp("2026-05-09")]


@pytest.mark.unit
def test_normalize_dates_leaves_naive_dates_at_midnight():
    naive = pd.Series(pd.to_datetime(["2026-05-08 14:30:00", "2026-05-09 00:00:00"]))
    out = ohlcv._normalize_dates(naive)
    assert out.dt.tz is None
    assert list(out) == [pd.Timestamp("2026-05-08"), pd.Timestamp("2026-05-09")]


@pytest.mark.unit
def test_normalize_dates_handles_mixed_dst_offsets():
    # 5y of US bars span DST; via a cache CSV they arrive as mixed-offset
    # strings, which pd.to_datetime can't unify. Each keeps its own local date.
    mixed = pd.Series([
        "2026-01-08 00:00:00-05:00",  # EST
        "2026-06-08 00:00:00-04:00",  # EDT
        "not-a-date",                 # -> NaT
    ])
    out = ohlcv._normalize_dates(mixed)
    assert out.iloc[0] == pd.Timestamp("2026-01-08")
    assert out.iloc[1] == pd.Timestamp("2026-06-08")
    assert pd.isna(out.iloc[2])


@pytest.mark.unit
def test_normalize_dates_keeps_positive_offset_local_date():
    # A Tokyo bar at local midnight (+09:00) must stay on its own calendar day,
    # not shift to the previous UTC day (which utc=True parsing would cause).
    jst = pd.Series(["2026-05-08 00:00:00+09:00"])
    assert ohlcv._normalize_dates(jst).iloc[0] == pd.Timestamp("2026-05-08")


# --- fill vs guard responsibilities ----------------------------------------

@pytest.mark.unit
def test_clean_dataframe_keeps_nan_close_for_the_caller_to_inspect():
    # _clean_dataframe normalizes but no longer drops the NaN close itself.
    df = pd.DataFrame({"Date": ["2026-05-08", "2026-05-09"], "Close": [100.0, float("nan")]})
    cleaned = ohlcv._clean_dataframe(df)
    assert len(cleaned) == 2
    assert pd.isna(cleaned["Close"].iloc[-1])


@pytest.mark.unit
def test_fill_price_gaps_drops_nan_close_rows():
    df = pd.DataFrame({"Date": pd.to_datetime(["2026-05-07", "2026-05-08"]),
                       "Close": [float("nan"), 100.0]})
    filled = ohlcv._fill_price_gaps(df)
    assert len(filled) == 1
    assert filled["Close"].iloc[0] == 100.0


# --- load_ohlcv end-to-end (with a mocked cache read) -----------------------

def _run_load(monkeypatch, tmp_path, frame, curr_date):
    """Drive load_ohlcv against a pre-seeded cache frame (no network)."""
    monkeypatch.setattr(ohlcv, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    today = pd.Timestamp(curr_date)
    monkeypatch.setattr(ohlcv.pd.Timestamp, "today", staticmethod(lambda: today))
    cache_file = tmp_path / "AAPL-YFin-data.csv"
    cache_file.write_text(frame.to_csv(index=False))
    _stamp(cache_file, today)

    def _fail_download(*a, **k):
        raise AssertionError("should use the seeded cache, not download")
    monkeypatch.setattr(ohlcv.yf, "download", _fail_download)
    return ohlcv.load_ohlcv("AAPL", curr_date)


@pytest.mark.unit
def test_unsettled_latest_bar_is_served_as_the_last_settled_bar(monkeypatch, tmp_path):
    # Newest bar (the curr_date) has no close: serve the last settled bar rather
    # than reporting the whole symbol as unavailable (#1289).
    frame = pd.DataFrame({
        "Date": ["2026-05-07", "2026-05-08"],
        "Open": [100.0, 101.0], "High": [101.0, 102.0], "Low": [99.0, 100.0],
        "Close": [100.5, float("nan")], "Volume": [1_000_000, 1_000_000],
    })
    out = _run_load(monkeypatch, tmp_path, frame, "2026-05-08")
    assert out["Date"].iloc[-1] == pd.Timestamp("2026-05-07")
    assert out["Close"].iloc[-1] == 100.5


@pytest.mark.unit
def test_no_settled_bar_at_all_is_still_no_data(monkeypatch, tmp_path):
    frame = pd.DataFrame({
        "Date": ["2026-05-07", "2026-05-08"],
        "Open": [100.0, 101.0], "High": [101.0, 102.0], "Low": [99.0, 100.0],
        "Close": [float("nan"), float("nan")], "Volume": [1_000_000, 1_000_000],
    })
    with pytest.raises(NoMarketDataError, match="no bar in range has a closing price"):
        _run_load(monkeypatch, tmp_path, frame, "2026-05-08")


@pytest.mark.unit
def test_serving_the_last_settled_bar_does_not_bypass_the_staleness_check(
    monkeypatch, tmp_path
):
    # Falling back must not resurrect a long-dead series: once the closeless
    # tail is gone, the remaining bar is judged on its age like any other.
    frame = pd.DataFrame({
        "Date": ["2026-01-05", "2026-05-08"],
        "Open": [100.0, 101.0], "High": [101.0, 102.0], "Low": [99.0, 100.0],
        "Close": [100.5, float("nan")], "Volume": [1_000_000, 1_000_000],
    })
    with pytest.raises(NoMarketDataError, match="stale"):
        _run_load(monkeypatch, tmp_path, frame, "2026-05-08")


@pytest.mark.unit
def test_older_nan_close_row_is_still_dropped(monkeypatch, tmp_path):
    # A stale gap mid-series is dropped; the valid latest bar is served.
    frame = pd.DataFrame({
        "Date": ["2026-05-06", "2026-05-07", "2026-05-08"],
        "Open": [100.0, 101.0, 102.0], "High": [101.0, 102.0, 103.0],
        "Low": [99.0, 100.0, 101.0],
        "Close": [100.5, float("nan"), 102.5], "Volume": [1_000_000, 1_000_000, 1_000_000],
    })
    out = _run_load(monkeypatch, tmp_path, frame, "2026-05-08")
    assert out["Close"].iloc[-1] == 102.5
    assert (out["Date"] == pd.Timestamp("2026-05-07")).sum() == 0  # the NaN row is gone


@pytest.mark.unit
def test_tz_aware_latest_bar_is_kept_at_the_cutoff(monkeypatch, tmp_path):
    # A tz-aware/intraday latest bar on the cutoff day must not be filtered out
    # by a naive-vs-aware comparison.
    frame = pd.DataFrame({
        "Date": ["2026-05-07 09:30:00-04:00", "2026-05-08 09:30:00-04:00"],
        "Open": [100.0, 101.0], "High": [101.0, 102.0], "Low": [99.0, 100.0],
        "Close": [100.5, 101.5], "Volume": [1_000_000, 1_000_000],
    })
    out = _run_load(monkeypatch, tmp_path, frame, "2026-05-08")
    assert out["Close"].iloc[-1] == 101.5
    assert out["Date"].iloc[-1] == pd.Timestamp("2026-05-08")


@pytest.mark.unit
def test_the_snapshot_does_not_present_a_filled_price_as_reported(monkeypatch, tmp_path):
    """Gap filling exists so indicators compute on a continuous series. The
    verification snapshot is the one place a number must be what the vendor
    reported, or the module built to stop invented prices supplies them."""
    from tradingagents.dataflows.vendors.yahoo import ohlcv, snapshot

    frame = pd.DataFrame({
        "Date": ["2026-05-06", "2026-05-07", "2026-05-08"],
        "Open": [100.0, 104.5, ""],     # the latest bar has not settled
        "High": [101.0, 105.5, ""],
        "Low": [99.0, 103.5, ""],
        "Close": [100.5, 105.0, 106.0],
        "Volume": [1000000, 1000000, ""],
    })
    today = pd.Timestamp("2026-05-08 12:00")
    monkeypatch.setattr(ohlcv, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(ohlcv.pd.Timestamp, "today", staticmethod(lambda: today))
    cache = tmp_path / "AAPL-YFin-data.csv"
    cache.write_text(frame.to_csv(index=False))
    _stamp(cache, today)
    monkeypatch.setattr(ohlcv.yf, "download", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("should read the seeded cache")))

    out = snapshot.build_verified_market_snapshot("AAPL", "2026-05-08", 3)

    row = out.split("Latest verified OHLCV row")[1].split("###")[0]
    assert "104.50" not in row and "105.50" not in row  # the previous session's numbers
    assert "106.00" in row  # the close the vendor did report
