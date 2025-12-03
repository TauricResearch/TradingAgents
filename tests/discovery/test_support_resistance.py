from unittest.mock import MagicMock, patch

import pytest


class TestFindSupportLevels:
    def test_find_support_from_lows(self):
        from tradingagents.agents.discovery.indicators.support_resistance import (
            find_support_levels,
        )

        lows = (
            [100.0, 98.0, 97.0, 99.0, 96.0, 95.0, 97.0, 98.0, 94.0, 93.0]
            + [95.0, 96.0, 94.0, 93.0, 92.0, 91.0, 90.0, 89.0, 88.0, 87.0]
            + [88.0, 89.0, 87.0, 86.0, 85.0] * 6
        )

        support_20d, support_50d = find_support_levels(
            lows, lookback_20=20, lookback_50=50
        )

        assert support_20d <= 100.0
        assert support_50d <= 100.0

    def test_find_support_empty_list(self):
        from tradingagents.agents.discovery.indicators.support_resistance import (
            find_support_levels,
        )

        lows = []
        support_20d, support_50d = find_support_levels(
            lows, lookback_20=20, lookback_50=50
        )

        assert support_20d == 0.0
        assert support_50d == 0.0


class TestFindResistanceLevels:
    def test_find_resistance_from_highs(self):
        from tradingagents.agents.discovery.indicators.support_resistance import (
            find_resistance_levels,
        )

        highs = (
            [100.0, 102.0, 105.0, 103.0, 108.0, 106.0, 110.0, 107.0, 112.0, 109.0]
            + [111.0, 113.0, 115.0, 114.0, 117.0, 116.0, 120.0, 118.0, 122.0, 119.0]
            + [120.0, 121.0, 123.0, 124.0, 125.0] * 6
        )

        resistance_20d, resistance_50d = find_resistance_levels(
            highs, lookback_20=20, lookback_50=50
        )

        assert resistance_20d >= 100.0
        assert resistance_50d >= 100.0

    def test_find_resistance_empty_list(self):
        from tradingagents.agents.discovery.indicators.support_resistance import (
            find_resistance_levels,
        )

        highs = []
        resistance_20d, resistance_50d = find_resistance_levels(
            highs, lookback_20=20, lookback_50=50
        )

        assert resistance_20d == 0.0
        assert resistance_50d == 0.0


class TestDetectSwingPoints:
    def test_detect_swing_highs_and_lows(self):
        from tradingagents.agents.discovery.indicators.support_resistance import (
            detect_swing_points,
        )

        prices = [
            100,
            102,
            105,
            103,
            98,
            95,
            97,
            100,
            103,
            107,
            105,
            102,
            99,
            96,
            94,
            97,
            101,
        ]
        swing_lows, swing_highs = detect_swing_points(prices, n_bars=3)

        assert len(swing_lows) >= 0
        assert len(swing_highs) >= 0

    def test_detect_swing_points_short_list(self):
        from tradingagents.agents.discovery.indicators.support_resistance import (
            detect_swing_points,
        )

        prices = [100, 105, 102]
        swing_lows, swing_highs = detect_swing_points(prices, n_bars=3)

        assert isinstance(swing_lows, list)
        assert isinstance(swing_highs, list)

    def test_detect_swing_points_empty_list(self):
        from tradingagents.agents.discovery.indicators.support_resistance import (
            detect_swing_points,
        )

        prices = []
        swing_lows, swing_highs = detect_swing_points(prices, n_bars=5)

        assert swing_lows == []
        assert swing_highs == []


class TestGetNearestLevels:
    def test_get_nearest_support_and_resistance(self):
        from tradingagents.agents.discovery.indicators.support_resistance import (
            get_nearest_levels,
        )

        price = 150.0
        supports = [140.0, 145.0, 130.0, 120.0]
        resistances = [155.0, 160.0, 170.0, 180.0]

        nearest_support, nearest_resistance = get_nearest_levels(
            price, supports, resistances
        )

        assert nearest_support == 145.0
        assert nearest_resistance == 155.0

    def test_get_nearest_levels_no_support_below(self):
        from tradingagents.agents.discovery.indicators.support_resistance import (
            get_nearest_levels,
        )

        price = 100.0
        supports = [110.0, 120.0, 130.0]
        resistances = [150.0, 160.0]

        nearest_support, nearest_resistance = get_nearest_levels(
            price, supports, resistances
        )

        assert nearest_support == 0.0
        assert nearest_resistance == 150.0

    def test_get_nearest_levels_empty_lists(self):
        from tradingagents.agents.discovery.indicators.support_resistance import (
            get_nearest_levels,
        )

        price = 150.0
        supports = []
        resistances = []

        nearest_support, nearest_resistance = get_nearest_levels(
            price, supports, resistances
        )

        assert nearest_support == 0.0
        assert nearest_resistance == 0.0


class TestCalculateSupportResistanceMetrics:
    @patch(
        "tradingagents.agents.discovery.indicators.support_resistance._get_ohlc_data"
    )
    @patch("tradingagents.agents.discovery.indicators.support_resistance._get_atr")
    def test_calculate_sr_metrics_returns_dict(self, mock_atr, mock_ohlc):
        from tradingagents.agents.discovery.indicators.support_resistance import (
            calculate_support_resistance_metrics,
        )

        mock_ohlc.return_value = {
            "highs": [105.0 + i * 0.5 for i in range(60)],
            "lows": [95.0 + i * 0.3 for i in range(60)],
            "closes": [100.0 + i * 0.4 for i in range(60)],
            "current_price": 125.0,
        }
        mock_atr.return_value = 2.5

        result = calculate_support_resistance_metrics("AAPL", "2024-01-15")

        assert isinstance(result, dict)
        assert "support_level" in result
        assert "resistance_level" in result
        assert "atr" in result
        assert "suggested_stop" in result
        assert "reward_target" in result
        assert "risk_reward_ratio" in result
        assert "risk_reward_score" in result

    @patch(
        "tradingagents.agents.discovery.indicators.support_resistance._get_ohlc_data"
    )
    @patch("tradingagents.agents.discovery.indicators.support_resistance._get_atr")
    def test_calculate_sr_metrics_handles_missing_data(self, mock_atr, mock_ohlc):
        from tradingagents.agents.discovery.indicators.support_resistance import (
            calculate_support_resistance_metrics,
        )

        mock_ohlc.return_value = {
            "highs": [],
            "lows": [],
            "closes": [],
            "current_price": None,
        }
        mock_atr.return_value = None

        result = calculate_support_resistance_metrics("INVALID", "2024-01-15")

        assert isinstance(result, dict)
        assert result["risk_reward_score"] == 0.5
