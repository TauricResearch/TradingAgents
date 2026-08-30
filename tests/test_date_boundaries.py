"""yfinance treats ``end`` as exclusive; we must request one extra day so the
requested end_date (and the current day) is actually included.

Regressions for #986 (current-day OHLCV excluded) and #987 (requested end_date
row omitted).
"""
import pandas as pd
import pytest

import tradingagents.dataflows.stockstats_utils as su
import tradingagents.dataflows.y_finance as yfin
from tradingagents.dataflows.config import set_config


@pytest.mark.unit
def test_get_yfin_requests_inclusive_end(monkeypatch):
    captured = {}

    class FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, start, end):
            captured["start"] = start
            captured["end"] = end
            idx = pd.to_datetime(["2025-05-08", "2025-05-09"])
            return pd.DataFrame(
                {"Open": [1.0, 2.0], "High": [1.0, 2.0], "Low": [1.0, 2.0],
                 "Close": [1.0, 2.0], "Volume": [1, 2]},
                index=idx,
            )

    monkeypatch.setattr(yfin.yf, "Ticker", FakeTicker)
    out = yfin.get_YFin_data_online("AAPL", "2025-05-01", "2025-05-09")

    # end is requested one day past end_date so 2025-05-09 is included (#987).
    assert captured["end"] == "2025-05-10"
    # Header still reflects the requested range, not the internal +1 day.
    assert "to 2025-05-09" in out


@pytest.mark.unit
def test_load_ohlcv_requests_inclusive_end(monkeypatch, tmp_path):
    set_config({"data_cache_dir": str(tmp_path)})
    captured = {}

    def fake_download(symbol, start, end, **kwargs):
        captured["end"] = end
        idx = pd.to_datetime([pd.Timestamp.today().normalize()])
        return pd.DataFrame(
            {"Open": [100.0], "High": [100.0], "Low": [100.0],
             "Close": [100.0], "Volume": [1]},
            index=idx,
        )

    monkeypatch.setattr(su.yf, "download", fake_download)
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    su.load_ohlcv("AAPL", today)

    expected_end = (pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    assert captured["end"] == expected_end  # tomorrow -> today's row included (#986)


@pytest.mark.unit
def test_backfill_latest_nan_bar_from_history(monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, period="1d"):
            return pd.DataFrame(
                {"Open": [150.0], "High": [155.0], "Low": [149.0], "Close": [153.0], "Volume": [5000000]},
                index=pd.to_datetime(["2026-08-03"]),
            )

    monkeypatch.setattr(su.yf, "Ticker", FakeTicker)
    df = pd.DataFrame(
        {
            "Date": ["2026-07-31", "2026-08-03"],
            "Open": [148.0, None],
            "High": [150.0, None],
            "Low": [147.0, None],
            "Close": [149.0, None],
            "Volume": [4000000, 5000000],
        }
    )
    res = su._backfill_latest_nan_bar(df, "AAPL")
    assert res.loc[1, "Close"] == 153.0
    assert res.loc[1, "Open"] == 150.0


@pytest.mark.unit
def test_backfill_latest_nan_bar_from_fast_info(monkeypatch):
    class FakeFastInfo:
        last_price = 154.5
        open = 151.0
        day_high = 156.0
        day_low = 150.0
        last_volume = 6000000

    class FakeTicker:
        def __init__(self, symbol):
            self.fast_info = FakeFastInfo()

        def history(self, period="1d"):
            return pd.DataFrame()

    monkeypatch.setattr(su.yf, "Ticker", FakeTicker)
    df = pd.DataFrame(
        {
            "Date": ["2026-07-31", "2026-08-03"],
            "Open": [148.0, None],
            "High": [150.0, None],
            "Low": [147.0, None],
            "Close": [149.0, None],
            "Volume": [4000000, 5000000],
        }
    )
    res = su._backfill_latest_nan_bar(df, "AAPL")
    assert res.loc[1, "Close"] == 154.5
    assert res.loc[1, "Open"] == 151.0


@pytest.mark.unit
def test_load_ohlcv_preserves_latest_day_with_nan_close(monkeypatch, tmp_path):
    """Ensure latest trading day is not dropped by dropna(subset=['Close']) (#1201)."""
    set_config({"data_cache_dir": str(tmp_path)})

    class FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, period="1d"):
            return pd.DataFrame(
                {"Open": [200.0], "High": [205.0], "Low": [199.0], "Close": [204.0], "Volume": [1000]},
                index=pd.to_datetime(["2026-08-03"]),
            )

    monkeypatch.setattr(su.yf, "Ticker", FakeTicker)

    def fake_download(symbol, start, end, **kwargs):
        idx = pd.to_datetime(["2026-07-31", "2026-08-03"])
        return pd.DataFrame(
            {
                "Open": [195.0, None],
                "High": [198.0, None],
                "Low": [194.0, None],
                "Close": [196.0, None],
                "Volume": [900, 1000],
            },
            index=idx,
        )

    monkeypatch.setattr(su.yf, "download", fake_download)
    out = su.load_ohlcv("AAPL", "2026-08-03")
    assert len(out) == 2
    assert pd.to_datetime(out["Date"].iloc[-1]) == pd.Timestamp("2026-08-03")
    assert out["Close"].iloc[-1] == 204.0
