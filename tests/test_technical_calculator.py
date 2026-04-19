# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the technical indicator pre-computation module (Issue #542)."""

from unittest.mock import patch, MagicMock

import pytest

from tradingagents.dataflows.technical_calculator import (
    compute_all_indicators,
    DEFAULT_INDICATORS,
    INDICATOR_CATEGORIES,
    _find_latest_date,
    _get_value,
)


# ---------------------------------------------------------------------------
# Helper: build a mock return value for _get_stock_stats_bulk
# ---------------------------------------------------------------------------

def _make_bulk_data(value: str, date: str = "2026-04-18") -> dict:
    """Return a simple {date: value} dict mimicking _get_stock_stats_bulk."""
    return {date: value}


# ---------------------------------------------------------------------------
# compute_all_indicators tests
# ---------------------------------------------------------------------------


@patch("tradingagents.dataflows.technical_calculator._get_stock_stats_bulk")
def test_compute_all_indicators_returns_markdown(mock_bulk):
    """Should return a Markdown-formatted string with all indicator categories."""
    mock_bulk.return_value = {"2026-04-18": "123.45"}

    result = compute_all_indicators("AAPL", "2026-04-18")

    assert "## Technical Indicators for AAPL" in result
    assert "### Moving Averages" in result
    assert "### MACD" in result
    assert "### Momentum" in result
    assert "### Volatility" in result
    assert "### Volume" in result
    assert "123.45" in result


@patch("tradingagents.dataflows.technical_calculator._get_stock_stats_bulk")
def test_compute_all_indicators_calls_bulk_for_each_indicator(mock_bulk):
    """Should call _get_stock_stats_bulk once per default indicator."""
    mock_bulk.return_value = {"2026-04-18": "10.0"}

    compute_all_indicators("AAPL", "2026-04-18")

    assert mock_bulk.call_count == len(DEFAULT_INDICATORS)


@patch("tradingagents.dataflows.technical_calculator._get_stock_stats_bulk")
def test_compute_all_indicators_graceful_degradation(mock_bulk):
    """If one indicator fails, the rest should still be computed."""
    call_count = 0

    def side_effect(symbol, indicator, curr_date):
        nonlocal call_count
        call_count += 1
        if indicator == "rsi":
            raise Exception("RSI calculation failed")
        return {"2026-04-18": "50.0"}

    mock_bulk.side_effect = side_effect

    result = compute_all_indicators("AAPL", "2026-04-18")

    # Should still produce output for other indicators
    assert "## Technical Indicators for AAPL" in result
    assert "50.00" in result
    # RSI should show N/A
    assert "N/A" in result


@patch("tradingagents.dataflows.technical_calculator._get_stock_stats_bulk")
def test_compute_all_indicators_no_data(mock_bulk):
    """If no data is available, should return a clear message."""
    mock_bulk.return_value = {}

    result = compute_all_indicators("AAPL", "2026-04-18")

    assert "No indicator data available" in result


@patch("tradingagents.dataflows.technical_calculator._get_stock_stats_bulk")
def test_compute_all_indicators_finds_previous_trading_day(mock_bulk):
    """Should look back up to 7 days to find a trading day with data."""
    # Data only available for Friday (2026-04-17), not weekend dates
    mock_bulk.return_value = {"2026-04-17": "100.0"}

    result = compute_all_indicators("AAPL", "2026-04-19")  # Sunday

    assert "2026-04-17" in result
    assert "100.00" in result


# ---------------------------------------------------------------------------
# RSI context tests
# ---------------------------------------------------------------------------


@patch("tradingagents.dataflows.technical_calculator._get_stock_stats_bulk")
def test_rsi_overbought_context(mock_bulk):
    """RSI >= 70 should show overbought context."""
    def side_effect(symbol, indicator, curr_date):
        if indicator == "rsi":
            return {"2026-04-18": "75.0"}
        return {"2026-04-18": "100.0"}

    mock_bulk.side_effect = side_effect

    result = compute_all_indicators("AAPL", "2026-04-18")

    assert "overbought" in result


@patch("tradingagents.dataflows.technical_calculator._get_stock_stats_bulk")
def test_rsi_oversold_context(mock_bulk):
    """RSI <= 30 should show oversold context."""
    def side_effect(symbol, indicator, curr_date):
        if indicator == "rsi":
            return {"2026-04-18": "25.0"}
        return {"2026-04-18": "100.0"}

    mock_bulk.side_effect = side_effect

    result = compute_all_indicators("AAPL", "2026-04-18")

    assert "oversold" in result


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


def test_default_indicators_count():
    """Should have all 12 indicators from the 5 categories."""
    expected = sum(len(inds) for inds in INDICATOR_CATEGORIES.values())
    assert len(DEFAULT_INDICATORS) == expected


def test_find_latest_date_exact_match():
    """Should return the exact date if data exists."""
    from datetime import datetime
    indicator_data = {"rsi": {"2026-04-18": "55.0"}}
    result = _find_latest_date(indicator_data, datetime(2026, 4, 18))
    assert result == "2026-04-18"


def test_find_latest_date_looks_back():
    """Should look back to find the nearest trading day."""
    from datetime import datetime
    indicator_data = {"rsi": {"2026-04-16": "55.0"}}
    result = _find_latest_date(indicator_data, datetime(2026, 4, 18))
    assert result == "2026-04-16"


def test_find_latest_date_no_data():
    """Should return None if no data within 7 days."""
    from datetime import datetime
    indicator_data = {"rsi": {"2026-04-01": "55.0"}}
    result = _find_latest_date(indicator_data, datetime(2026, 4, 18))
    assert result is None


def test_get_value_formats_float():
    """Should format numeric values to 2 decimal places."""
    data = {"rsi": {"2026-04-18": "55.123456"}}
    result = _get_value(data, "rsi", "2026-04-18")
    assert result == "55.12"


def test_get_value_handles_na():
    """Should return N/A for missing data."""
    result = _get_value({}, "rsi", "2026-04-18")
    assert result == "N/A"
