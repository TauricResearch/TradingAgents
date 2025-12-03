from unittest.mock import MagicMock, patch

import pytest


class TestCalculateRsiScore:
    def test_rsi_oversold_bullish_score(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_rsi_score,
        )

        score = calculate_rsi_score(25.0)
        assert 0.8 <= score <= 1.0

        score = calculate_rsi_score(30.0)
        assert 0.7 <= score <= 0.9

    def test_rsi_neutral_score(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_rsi_score,
        )

        score = calculate_rsi_score(50.0)
        assert 0.5 <= score <= 0.7

        score = calculate_rsi_score(40.0)
        assert 0.5 <= score <= 0.7

    def test_rsi_overbought_warning_score(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_rsi_score,
        )

        score = calculate_rsi_score(70.0)
        assert 0.3 <= score <= 0.5

        score = calculate_rsi_score(75.0)
        assert 0.2 <= score <= 0.5

    def test_rsi_extreme_overbought_score(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_rsi_score,
        )

        score = calculate_rsi_score(85.0)
        assert 0.0 <= score <= 0.3

        score = calculate_rsi_score(95.0)
        assert 0.0 <= score <= 0.2


class TestCalculateMacdScore:
    def test_macd_bullish_crossover_high_score(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_macd_score,
        )

        score = calculate_macd_score(macd=1.5, signal=1.0, histogram=0.5)
        assert 0.7 <= score <= 1.0

    def test_macd_bearish_crossover_low_score(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_macd_score,
        )

        score = calculate_macd_score(macd=-1.5, signal=-1.0, histogram=-0.5)
        assert 0.0 <= score <= 0.4

    def test_macd_neutral_score(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_macd_score,
        )

        score = calculate_macd_score(macd=0.1, signal=0.1, histogram=0.0)
        assert 0.4 <= score <= 0.6

    def test_macd_expanding_histogram_bullish(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_macd_score,
        )

        score = calculate_macd_score(macd=2.0, signal=1.5, histogram=0.8)
        assert 0.6 <= score <= 1.0


class TestCalculateSmaScore:
    def test_price_above_both_smas_high_score(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_sma_score,
        )

        score = calculate_sma_score(price=150.0, sma50=140.0, sma200=130.0)
        assert 0.7 <= score <= 1.0

    def test_price_below_both_smas_low_score(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_sma_score,
        )

        score = calculate_sma_score(price=120.0, sma50=140.0, sma200=150.0)
        assert 0.0 <= score <= 0.4

    def test_price_between_smas_moderate_score(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_sma_score,
        )

        score = calculate_sma_score(price=145.0, sma50=150.0, sma200=130.0)
        assert 0.4 <= score <= 0.7

    def test_golden_alignment_bonus(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_sma_score,
        )

        score = calculate_sma_score(price=160.0, sma50=150.0, sma200=140.0)
        assert score >= 0.8


class TestCalculateEmaDirection:
    def test_ema_upward_trend(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_ema_direction,
        )

        ema_values = [100.0, 102.0, 104.0, 106.0, 108.0]
        direction = calculate_ema_direction(ema_values)
        assert direction == "up"

    def test_ema_downward_trend(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_ema_direction,
        )

        ema_values = [108.0, 106.0, 104.0, 102.0, 100.0]
        direction = calculate_ema_direction(ema_values)
        assert direction == "down"

    def test_ema_flat_trend(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_ema_direction,
        )

        ema_values = [100.0, 100.1, 99.9, 100.0, 100.1]
        direction = calculate_ema_direction(ema_values)
        assert direction == "flat"

    def test_ema_empty_list_returns_flat(self):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_ema_direction,
        )

        ema_values = []
        direction = calculate_ema_direction(ema_values)
        assert direction == "flat"


class TestCalculateMomentumScore:
    @patch("tradingagents.agents.discovery.indicators.momentum._get_stock_stats_bulk")
    def test_calculate_momentum_score_returns_dict(self, mock_get_stats):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_momentum_score,
        )

        mock_get_stats.side_effect = lambda symbol, indicator, date: {
            "2024-01-15": "50.0" if indicator == "rsi" else "1.0",
            "2024-01-14": "49.0" if indicator == "rsi" else "0.9",
            "2024-01-13": "48.0" if indicator == "rsi" else "0.8",
            "2024-01-12": "47.0" if indicator == "rsi" else "0.7",
            "2024-01-11": "46.0" if indicator == "rsi" else "0.6",
        }

        result = calculate_momentum_score("AAPL", "2024-01-15")

        assert isinstance(result, dict)
        assert "rsi" in result
        assert "macd" in result
        assert "macd_signal" in result
        assert "macd_histogram" in result
        assert "price_vs_sma50" in result
        assert "price_vs_sma200" in result
        assert "ema10_direction" in result
        assert "momentum_score" in result
        assert 0.0 <= result["momentum_score"] <= 1.0

    @patch("tradingagents.agents.discovery.indicators.momentum._get_stock_stats_bulk")
    def test_calculate_momentum_score_handles_missing_data(self, mock_get_stats):
        from tradingagents.agents.discovery.indicators.momentum import (
            calculate_momentum_score,
        )

        mock_get_stats.return_value = {}

        result = calculate_momentum_score("INVALID", "2024-01-15")

        assert isinstance(result, dict)
        assert result["momentum_score"] == 0.5
