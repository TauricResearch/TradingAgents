"""Tests for the OHLCV plausibility guard and retry loop in _load_or_fetch_ohlcv."""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def _make_df(close_values: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(close_values), freq="B")
    return pd.DataFrame({
        "Date": dates.strftime("%Y-%m-%d"),
        "Open": close_values, "High": close_values,
        "Low": close_values, "Close": close_values, "Volume": [1_000_000] * len(close_values),
    })


def test_is_close_plausible_detects_contamination():
    """_is_close_plausible returns False when rolling mean is 5× the last close."""
    from tradingagents.dataflows.stockstats_utils import _is_close_plausible

    # Last close is $36, but rolling mean is $170 — contamination scenario
    closes = [170.0] * 49 + [36.0]
    df = _make_df(closes)
    assert _is_close_plausible(df, "STM") is False


def test_is_close_plausible_passes_normal_data():
    """_is_close_plausible returns True for stable close prices."""
    from tradingagents.dataflows.stockstats_utils import _is_close_plausible

    closes = [100.0 + i * 0.1 for i in range(60)]
    df = _make_df(closes)
    assert _is_close_plausible(df, "AAPL") is True


def test_load_or_fetch_ohlcv_retries_on_plausibility_failure(tmp_path, monkeypatch):
    """_load_or_fetch_ohlcv retries download up to 3 times when plausibility check fails."""
    from tradingagents.dataflows import stockstats_utils as su

    monkeypatch.setattr(su, "get_config", lambda: {"data_cache_dir": str(tmp_path)})

    bad_df = _make_df([170.0] * 49 + [36.0])  # contaminated: last close $36, mean $170
    mock_raw = MagicMock()
    mock_raw.empty = False
    mock_raw.reset_index.return_value = bad_df

    with patch.object(su, "yf") as mock_yf:
        mock_yf.download.return_value = mock_raw
        with pytest.raises(RuntimeError, match=r"\[OHLCV\] Plausibility check failed"):
            su._load_or_fetch_ohlcv("STM")
        assert mock_yf.download.call_count == 3, "Should have retried exactly 3 times"


def test_load_or_fetch_ohlcv_accepts_data_after_retry(tmp_path, monkeypatch):
    """_load_or_fetch_ohlcv succeeds on the second attempt after one plausibility failure."""
    from tradingagents.dataflows import stockstats_utils as su

    monkeypatch.setattr(su, "get_config", lambda: {"data_cache_dir": str(tmp_path)})

    bad_df = _make_df([170.0] * 49 + [36.0])
    good_df = _make_df([36.0] * 60)

    call_count = {"n": 0}
    def fake_download(*args, **kwargs):
        call_count["n"] += 1
        m = MagicMock()
        m.empty = False
        m.reset_index.return_value = bad_df if call_count["n"] == 1 else good_df
        return m

    with patch.object(su, "yf") as mock_yf:
        mock_yf.download.side_effect = fake_download
        result = su._load_or_fetch_ohlcv("STM")
        assert mock_yf.download.call_count == 2
        assert len(result) == 60
