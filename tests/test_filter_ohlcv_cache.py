"""Tests for OHLCV-cache-backed filter enrichment."""
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

# 200-day SMA lookback + 10-day buffer — minimum rows needed for filter checks
_BASELINE_ROWS = 210


def _make_ohlcv(closes: list[float]) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame from a list of closing prices."""
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="B")
    opens = [c * 0.995 for c in closes]
    highs = [c * 1.005 for c in closes]
    lows = [c * 0.990 for c in closes]
    return pd.DataFrame(
        {
            "Open": opens,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": [1_000_000] * len(closes),
        },
        index=dates,
    )


def _make_filter(config_overrides=None):
    """Instantiate a CandidateFilter with minimal config."""
    from tradingagents.dataflows.discovery.filter import CandidateFilter

    config = {
        "discovery": {
            "ohlcv_cache_dir": "data/ohlcv_cache",
            "filters": {
                "min_average_volume": 0,
                "volume_lookback_days": 10,
                "filter_same_day_movers": True,
                "intraday_movement_threshold": 10.0,
                "filter_recent_movers": True,
                "recent_movement_lookback_days": 7,
                "recent_movement_threshold": 10.0,
                "recent_mover_action": "filter",
                "volume_cache_key": "default",
                "min_market_cap": 0,
                "compression_atr_pct_max": 2.0,
                "compression_bb_width_max": 6.0,
                "compression_min_volume_ratio": 1.3,
                "filter_fundamental_risk": False,
                "min_z_score": None,
                "min_f_score": None,
            },
            "enrichment": {
                "batch_news_vendor": "google",
                "batch_news_batch_size": 150,
                "news_lookback_days": 0.5,
                "context_max_snippets": 2,
                "context_snippet_max_chars": 140,
            },
            "max_candidates_to_analyze": 200,
            "analyze_all_candidates": False,
            "final_recommendations": 15,
            "truncate_ranking_context": False,
            "max_news_chars": 500,
            "max_insider_chars": 300,
            "max_recommendations_chars": 300,
            "log_tool_calls": False,
            "log_tool_calls_console": False,
            "log_prompts_console": False,
            "tool_log_max_chars": 10_000,
            "tool_log_exclude": [],
        }
    }
    if config_overrides:
        config["discovery"]["filters"].update(config_overrides)

    # Create a mock tool executor
    mock_tool_executor = MagicMock()

    return CandidateFilter(config, mock_tool_executor)


def test_current_price_comes_from_ohlcv_cache():
    """current_price on the candidate should be the last close from the OHLCV cache."""
    closes = [100.0] * _BASELINE_ROWS + [123.45]  # last close = 123.45
    ohlcv_data = {"AAPL": _make_ohlcv(closes)}

    f = _make_filter()
    price = f._price_from_cache("AAPL", ohlcv_data)
    assert price == pytest.approx(123.45)


def test_intraday_check_from_cache_not_moved():
    """intraday check: <10% day-over-day change → already_moved=False."""
    closes = [100.0] * _BASELINE_ROWS + [105.0]  # +5% last day — under threshold
    ohlcv_data = {"AAPL": _make_ohlcv(closes)}

    f = _make_filter()
    result = f._intraday_from_cache("AAPL", ohlcv_data, threshold=10.0)
    assert result["already_moved"] is False
    assert result["intraday_change_pct"] == pytest.approx(5.0)


def test_intraday_check_from_cache_moved():
    """intraday check: >10% day-over-day change → already_moved=True."""
    closes = [100.0] * _BASELINE_ROWS + [115.0]  # +15% last day — over threshold
    ohlcv_data = {"AAPL": _make_ohlcv(closes)}

    f = _make_filter()
    result = f._intraday_from_cache("AAPL", ohlcv_data, threshold=10.0)
    assert result["already_moved"] is True
    assert result["intraday_change_pct"] == pytest.approx(15.0)


def test_recent_move_check_from_cache_leading():
    """recent-move check: <10% change over 7 days → status=leading."""
    closes = [100.0] * (_BASELINE_ROWS - 5) + [103.0] * 7  # +3% change within the 7-day lookback window — under the 10% threshold
    ohlcv_data = {"AAPL": _make_ohlcv(closes)}

    f = _make_filter()
    result = f._recent_move_from_cache("AAPL", ohlcv_data, lookback_days=7, threshold=10.0)
    assert result["status"] == "leading"
    assert abs(result["price_change_pct"]) < 10.0


def test_recent_move_check_from_cache_lagging():
    """recent-move check: >10% change over 7 days → status=lagging."""
    closes = [100.0] * (_BASELINE_ROWS - 5) + [100.0] * 6 + [115.0]  # +15% in last day within window
    ohlcv_data = {"AAPL": _make_ohlcv(closes)}

    f = _make_filter()
    result = f._recent_move_from_cache("AAPL", ohlcv_data, lookback_days=7, threshold=10.0)
    assert result["status"] == "lagging"
    assert result["price_change_pct"] == pytest.approx(15.0)


def test_cache_miss_returns_none():
    """If ticker is not in ohlcv_data, helper returns None."""
    f = _make_filter()
    assert f._price_from_cache("MISSING", {}) is None
    assert f._intraday_from_cache("MISSING", {}, threshold=10.0) is None
    assert f._recent_move_from_cache("MISSING", {}, lookback_days=7, threshold=10.0) is None
