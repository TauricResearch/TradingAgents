import pandas as pd
import pytest
from unittest.mock import patch

from tradingagents.dataflows.range_stats import (
    compute_range_stats,
    RangeStatsUnavailable,
)

from tradingagents.dataflows.range_stats import (
    format_range_stats_markdown,
    format_range_stats_for_webui,
    format_range_stats_telegram,
    _color_for_window,
)


def _fake_ohlcv(rows: int, last_date="2026-05-06") -> pd.DataFrame:
    """Build a deterministic OHLCV frame ending on `last_date`."""
    end = pd.Timestamp(last_date)
    dates = pd.bdate_range(end=end, periods=rows)
    return pd.DataFrame(
        {
            "Date": dates.strftime("%Y-%m-%d"),
            "Open": [100 + i for i in range(rows)],
            "High": [101 + i for i in range(rows)],
            "Low": [99 + i for i in range(rows)],
            "Close": [100.5 + i for i in range(rows)],
            "Volume": [1_000_000 + i * 1000 for i in range(rows)],
        }
    )


@patch("tradingagents.dataflows.range_stats._load_ohlcv")
def test_basic_shape_with_full_history(mock_load):
    mock_load.return_value = _fake_ohlcv(260)  # > 252 trading days
    stats = compute_range_stats("FAKE", "2026-05-06")
    assert stats["symbol"] == "FAKE"
    assert stats["trade_date"] == "2026-05-06"
    assert set(stats["metrics"].keys()) == {"open", "close", "volume"}
    for metric in ("open", "close", "volume"):
        windows = stats["metrics"][metric]
        assert set(windows.keys()) == {"52w", "6m", "3m", "1m"}
        for w in ("52w", "6m", "3m", "1m"):
            row = windows[w]
            assert set(row.keys()) == {
                "low", "high", "pct_above_low", "pct_below_high", "position_pct"
            }


@patch("tradingagents.dataflows.range_stats._load_ohlcv")
def test_close_percentages_against_known_window(mock_load):
    """1m window = last 21 trading days. Build a frame where today's close is 120
    (the high) and the prior 20 closes range exactly 100..119."""
    df = pd.DataFrame(
        {
            "Date": pd.bdate_range(end="2026-05-06", periods=21).strftime("%Y-%m-%d"),
            "Open": [100.0] * 21,
            "High": [120.0] * 21,
            "Low": [100.0] * 21,
            "Close": list(range(100, 121)),  # 100..120, close today=120
            "Volume": [1] * 21,
        }
    )
    mock_load.return_value = df
    stats = compute_range_stats("FAKE", "2026-05-06")
    m1 = stats["metrics"]["close"]["1m"]
    # close today=120, 1m low=100, 1m high=120
    assert m1["low"] == pytest.approx(100.0)
    assert m1["high"] == pytest.approx(120.0)
    assert m1["pct_above_low"] == pytest.approx(20.0)
    assert m1["pct_below_high"] == pytest.approx(0.0)
    assert m1["position_pct"] == pytest.approx(100.0)


@patch("tradingagents.dataflows.range_stats._load_ohlcv")
def test_partial_history_marks_only_unavailable_windows(mock_load):
    """100 trading days → 1m and 3m valid, 6m and 52w n/a."""
    mock_load.return_value = _fake_ohlcv(100)
    stats = compute_range_stats("FAKE", "2026-05-06")
    for metric in ("open", "close", "volume"):
        assert stats["metrics"][metric]["1m"]["low"] is not None
        assert stats["metrics"][metric]["3m"]["low"] is not None
        assert stats["metrics"][metric]["6m"]["low"] is None
        assert stats["metrics"][metric]["52w"]["low"] is None


@patch("tradingagents.dataflows.range_stats._load_ohlcv")
def test_high_equals_low_position_falls_back_to_50(mock_load):
    df = pd.DataFrame(
        {
            "Date": pd.bdate_range(end="2026-05-06", periods=21).strftime("%Y-%m-%d"),
            "Open": [100.0] * 21,
            "High": [100.0] * 21,
            "Low": [100.0] * 21,
            "Close": [100.0] * 21,
            "Volume": [0] * 21,
        }
    )
    mock_load.return_value = df
    stats = compute_range_stats("FAKE", "2026-05-06")
    m1 = stats["metrics"]["close"]["1m"]
    assert m1["position_pct"] == pytest.approx(50.0)
    # volume=0 across the window → pct_above_low must be n/a (None)
    v1 = stats["metrics"]["volume"]["1m"]
    assert v1["pct_above_low"] is None


@patch("tradingagents.dataflows.range_stats._load_ohlcv")
def test_trade_date_on_weekend_uses_last_trading_row(mock_load):
    df = _fake_ohlcv(30, last_date="2026-05-01")  # Friday
    mock_load.return_value = df
    stats = compute_range_stats("FAKE", "2026-05-03")  # Sunday
    # Should use 2026-05-01's close, not raise
    assert stats["today"]["close"] is not None
    assert stats["today"]["effective_date"] == "2026-05-01"


@patch("tradingagents.dataflows.range_stats._load_ohlcv")
def test_no_data_at_all_raises(mock_load):
    mock_load.return_value = pd.DataFrame()
    with pytest.raises(RangeStatsUnavailable):
        compute_range_stats("NOPE", "2026-05-06")


def _sample_stats():
    return {
        "symbol": "AAPL",
        "trade_date": "2026-05-06",
        "today": {
            "effective_date": "2026-05-06",
            "open": 189.23,
            "close": 192.15,
            "volume": 58_231_400,
        },
        "metrics": {
            "close": {
                "52w": {"low": 164.20, "high": 215.40,
                        "pct_above_low": 17.0, "pct_below_high": -10.8, "position_pct": 54.5},
                "6m":  {"low": 170.10, "high": 215.40,
                        "pct_above_low": 12.9, "pct_below_high": -10.8, "position_pct": 48.6},
                "3m":  {"low": 178.50, "high": 210.00,
                        "pct_above_low": 7.6,  "pct_below_high": -8.5,  "position_pct": 43.3},
                "1m":  {"low": 184.00, "high": 198.20,
                        "pct_above_low": 4.4,  "pct_below_high": -3.0,  "position_pct": 57.4},
            },
            "open": {
                "52w": {"low": None, "high": None,
                        "pct_above_low": None, "pct_below_high": None, "position_pct": None},
                "6m":  {"low": 170.10, "high": 215.40,
                        "pct_above_low": 11.2, "pct_below_high": -12.1, "position_pct": 42.0},
                "3m":  {"low": 178.50, "high": 210.00,
                        "pct_above_low": 6.0, "pct_below_high": -9.9, "position_pct": 34.0},
                "1m":  {"low": 184.00, "high": 198.20,
                        "pct_above_low": 2.8, "pct_below_high": -4.5, "position_pct": 36.8},
            },
            "volume": {
                "52w": {"low": 26_000_000, "high": 105_000_000,
                        "pct_above_low": 124.0, "pct_below_high": -44.5, "position_pct": 40.8},
                "6m":  {"low": 28_000_000, "high": 90_000_000,
                        "pct_above_low": 108.0, "pct_below_high": -35.3, "position_pct": 48.8},
                "3m":  {"low": 30_000_000, "high": 80_000_000,
                        "pct_above_low": 94.1, "pct_below_high": -27.2, "position_pct": 56.5},
                "1m":  {"low": 35_000_000, "high": 70_000_000,
                        "pct_above_low": 66.4, "pct_below_high": -16.8, "position_pct": 66.4},
            },
        },
    }


def test_markdown_contains_three_section_headers_and_today_line():
    md = format_range_stats_markdown(_sample_stats())
    assert "Range Stats for AAPL on 2026-05-06" in md
    assert "Today: open=189.23" in md
    assert "## Close (192.15)" in md
    assert "## Open (189.23)" in md
    assert "## Volume (58,231,400)" in md
    assert "| 52w" in md
    assert "n/a" in md  # the open 52w window has None values


def test_markdown_renders_signed_percentages_with_one_decimal():
    md = format_range_stats_markdown(_sample_stats())
    assert "+17.0%" in md
    assert "-10.8%" in md
    assert "54.5%" in md


def test_webui_dict_includes_color_hints_for_extremes():
    payload = format_range_stats_for_webui(_sample_stats())
    # close 1m position_pct = 57.4 → not extreme → no color
    close_1m = payload["metrics"]["close"]["1m"]
    assert close_1m["color"] is None
    # volume 1m position_pct = 66.4 → still no color hint (threshold is >80)
    # construct an extreme entry to verify
    extreme = {
        "low": 10, "high": 20, "pct_above_low": 100.0,
        "pct_below_high": -2.0, "position_pct": 95.0,
    }
    assert _color_for_window(extreme) == "red"
    extreme_low = {
        "low": 10, "high": 20, "pct_above_low": 1.0,
        "pct_below_high": -50.0, "position_pct": 5.0,
    }
    assert _color_for_window(extreme_low) == "green"


def test_telegram_format_is_compact_four_lines():
    msg = format_range_stats_telegram(_sample_stats())
    # Header + 3 metric lines
    lines = [ln for ln in msg.splitlines() if ln.strip()]
    assert len(lines) == 4
    assert "AAPL" in lines[0] and "2026-05-06" in lines[0]
    assert lines[1].startswith("Close")
    assert lines[2].startswith("Open")
    assert lines[3].startswith("Vol")
    # Volume row uses readable 58.2M, not raw integer
    assert "58.2M" in lines[3]
