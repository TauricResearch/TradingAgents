from unittest.mock import MagicMock, patch

import pytest


class TestCalculateVolumeRatio:
    def test_volume_ratio_above_average(self):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_volume_ratio,
        )

        ratio = calculate_volume_ratio(
            current_volume=2_000_000, avg_volume_20d=1_000_000
        )
        assert ratio == 2.0

    def test_volume_ratio_below_average(self):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_volume_ratio,
        )

        ratio = calculate_volume_ratio(current_volume=500_000, avg_volume_20d=1_000_000)
        assert ratio == 0.5

    def test_volume_ratio_zero_average_returns_zero(self):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_volume_ratio,
        )

        ratio = calculate_volume_ratio(current_volume=1_000_000, avg_volume_20d=0)
        assert ratio == 0.0


class TestCalculateVolumeTrend:
    def test_volume_trend_increasing(self):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_volume_trend,
        )

        volume_series = [100_000, 150_000, 200_000, 250_000, 300_000]
        trend, slope = calculate_volume_trend(volume_series)
        assert trend == "increasing"
        assert slope > 0

    def test_volume_trend_decreasing(self):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_volume_trend,
        )

        volume_series = [300_000, 250_000, 200_000, 150_000, 100_000]
        trend, slope = calculate_volume_trend(volume_series)
        assert trend == "decreasing"
        assert slope < 0

    def test_volume_trend_flat(self):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_volume_trend,
        )

        volume_series = [100_000, 100_100, 99_900, 100_050, 99_950]
        trend, slope = calculate_volume_trend(volume_series)
        assert trend == "flat"

    def test_volume_trend_empty_returns_flat(self):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_volume_trend,
        )

        volume_series = []
        trend, slope = calculate_volume_trend(volume_series)
        assert trend == "flat"
        assert slope == 0.0


class TestCalculateDollarVolume:
    def test_dollar_volume_calculation(self):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_dollar_volume,
        )

        dollar_vol = calculate_dollar_volume(price=150.0, volume=1_000_000)
        assert dollar_vol == 150_000_000.0

    def test_dollar_volume_zero_price(self):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_dollar_volume,
        )

        dollar_vol = calculate_dollar_volume(price=0.0, volume=1_000_000)
        assert dollar_vol == 0.0


class TestCalculateVolumeScore:
    def test_volume_spike_with_positive_price_high_score(self):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_volume_score,
        )

        score = calculate_volume_score(
            volume_ratio=2.5,
            trend="increasing",
            dollar_volume=50_000_000.0,
            price_change=5.0,
            min_dollar_volume=1_000_000.0,
        )
        assert 0.8 <= score <= 1.0

    def test_above_average_volume_moderate_score(self):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_volume_score,
        )

        score = calculate_volume_score(
            volume_ratio=1.5,
            trend="increasing",
            dollar_volume=10_000_000.0,
            price_change=2.0,
            min_dollar_volume=1_000_000.0,
        )
        assert 0.7 <= score <= 0.9

    def test_normal_volume_neutral_score(self):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_volume_score,
        )

        score = calculate_volume_score(
            volume_ratio=1.0,
            trend="flat",
            dollar_volume=5_000_000.0,
            price_change=0.5,
            min_dollar_volume=1_000_000.0,
        )
        assert 0.3 <= score <= 0.6

    def test_low_dollar_volume_penalized(self):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_volume_score,
        )

        high_volume_score = calculate_volume_score(
            volume_ratio=2.0,
            trend="increasing",
            dollar_volume=50_000_000.0,
            price_change=3.0,
            min_dollar_volume=1_000_000.0,
        )

        low_volume_score = calculate_volume_score(
            volume_ratio=2.0,
            trend="increasing",
            dollar_volume=500_000.0,
            price_change=3.0,
            min_dollar_volume=1_000_000.0,
        )

        assert low_volume_score < high_volume_score


class TestCalculateVolumeMetrics:
    @patch("tradingagents.agents.discovery.indicators.volume._get_volume_price_data")
    def test_calculate_volume_metrics_returns_dict(self, mock_get_data):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_volume_metrics,
        )

        mock_get_data.return_value = {
            "volumes": [1_000_000] * 25,
            "prices": [100.0] * 25,
            "current_price": 105.0,
            "current_volume": 1_500_000,
            "price_change_pct": 5.0,
        }

        result = calculate_volume_metrics("AAPL", "2024-01-15")

        assert isinstance(result, dict)
        assert "volume_ratio" in result
        assert "volume_trend" in result
        assert "dollar_volume" in result
        assert "volume_score" in result
        assert 0.0 <= result["volume_score"] <= 1.0

    @patch("tradingagents.agents.discovery.indicators.volume._get_volume_price_data")
    def test_calculate_volume_metrics_handles_missing_data(self, mock_get_data):
        from tradingagents.agents.discovery.indicators.volume import (
            calculate_volume_metrics,
        )

        mock_get_data.return_value = {
            "volumes": [],
            "prices": [],
            "current_price": None,
            "current_volume": None,
            "price_change_pct": 0.0,
        }

        result = calculate_volume_metrics("INVALID", "2024-01-15")

        assert isinstance(result, dict)
        assert result["volume_score"] == 0.5
