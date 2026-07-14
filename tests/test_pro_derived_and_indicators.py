"""Deterministic math: derived features and the indicator engine."""

import pytest

from tests.pro_fakes import make_bars
from tradingagents.contracts import Timeframe
from tradingagents.pro.ingestion.derived import (
    bars_to_dataframe,
    orderbook_imbalance,
    pearson_correlation,
)
from tradingagents.pro.ingestion.indicators import compute_indicators


class TestPearsonCorrelation:
    def test_perfect_positive(self):
        assert pearson_correlation([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)

    def test_perfect_negative(self):
        assert pearson_correlation([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)

    def test_known_value(self):
        # hand-computed: r of (1,2,3) vs (1,3,2) = 0.5
        assert pearson_correlation([1, 2, 3], [1, 3, 2]) == pytest.approx(0.5)

    def test_length_mismatch_rejected(self):
        with pytest.raises(ValueError, match="mismatch"):
            pearson_correlation([1, 2, 3], [1, 2])

    def test_too_few_points_rejected(self):
        with pytest.raises(ValueError, match="at least 3"):
            pearson_correlation([1, 2], [3, 4])

    def test_zero_variance_rejected(self):
        with pytest.raises(ValueError, match="zero-variance"):
            pearson_correlation([5, 5, 5], [1, 2, 3])


class TestOrderbookImbalance:
    def test_all_bid(self):
        assert orderbook_imbalance([(100.0, 5.0)], []) == 1.0

    def test_all_ask(self):
        assert orderbook_imbalance([], [(101.0, 5.0)]) == -1.0

    def test_balanced(self):
        assert orderbook_imbalance([(100.0, 3.0)], [(101.0, 3.0)]) == 0.0

    def test_weighted(self):
        # bids 6, asks 2 -> (6-2)/8 = 0.5
        value = orderbook_imbalance([(100.0, 4.0), (99.5, 2.0)], [(101.0, 2.0)])
        assert value == pytest.approx(0.5)

    def test_empty_book_rejected(self):
        with pytest.raises(ValueError, match="empty order book"):
            orderbook_imbalance([], [])


class TestIndicatorEngine:
    def test_computes_default_set_on_sufficient_history(self):
        bars = make_bars(n=250)
        readings = compute_indicators(bars)
        names = {r.name for r in readings}
        assert {"RSI_14", "EMA_10", "SMA_50", "SMA_200", "MACD", "BOLL", "ATR_14"} <= names

    def test_sma_matches_manual_mean(self):
        bars = make_bars(n=60)
        readings = {r.name: r for r in compute_indicators(bars, ["SMA_50"])}
        manual = sum(b.close for b in bars[-50:]) / 50
        assert readings["SMA_50"].value["value"] == pytest.approx(manual)

    def test_rsi_of_monotonic_rise_is_high(self):
        readings = {r.name: r for r in compute_indicators(make_bars(n=60), ["RSI_14"])}
        rsi = readings["RSI_14"].value["value"]
        assert 90 < rsi <= 100

    def test_macd_groups_three_lines(self):
        readings = {r.name: r for r in compute_indicators(make_bars(n=60), ["MACD"])}
        assert set(readings["MACD"].value) == {"macd", "signal", "histogram"}

    def test_warmup_exceeding_history_is_skipped_not_garbage(self):
        readings = compute_indicators(make_bars(n=60), ["SMA_200", "RSI_14"])
        names = {r.name for r in readings}
        assert "SMA_200" not in names
        assert "RSI_14" in names

    def test_unknown_indicator_rejected(self):
        with pytest.raises(ValueError, match="unknown indicator"):
            compute_indicators(make_bars(n=30), ["ICHIMOKU"])

    def test_mixed_timeframes_rejected(self):
        bars = make_bars(n=30, timeframe=Timeframe.D1) + make_bars(n=30, timeframe=Timeframe.H4)
        with pytest.raises(ValueError, match="multiple timeframes"):
            compute_indicators(bars)

    def test_readings_carry_timeframe_and_params(self):
        readings = {r.name: r for r in compute_indicators(make_bars(n=60), ["RSI_14"])}
        assert readings["RSI_14"].timeframe is Timeframe.D1
        assert readings["RSI_14"].params == {"period": 14}


def test_bars_to_dataframe_sorted_and_shaped():
    bars = make_bars(n=5)
    frame = bars_to_dataframe(reversed(bars))
    assert list(frame.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert frame["close"].is_monotonic_increasing


def test_bars_to_dataframe_rejects_empty():
    import pytest

    with pytest.raises(ValueError, match="no bars"):
        bars_to_dataframe([])
