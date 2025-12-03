import pytest
from pydantic import ValidationError

from tradingagents.agents.discovery.quantitative_models import QuantitativeMetrics


class TestQuantitativeMetricsInstantiation:
    def test_model_instantiation_with_valid_data(self):
        metrics = QuantitativeMetrics(
            momentum_score=0.75,
            volume_score=0.60,
            relative_strength_score=0.80,
            risk_reward_score=0.70,
            rsi=45.5,
            macd=0.25,
            macd_signal=0.20,
            macd_histogram=0.05,
            price_vs_sma50=5.2,
            price_vs_sma200=12.3,
            ema10_direction="up",
            volume_ratio=1.8,
            volume_trend="increasing",
            dollar_volume=15_000_000.0,
            rs_vs_spy_5d=2.5,
            rs_vs_spy_20d=5.0,
            rs_vs_spy_60d=8.2,
            rs_vs_sector=3.1,
            sector_etf="XLK",
            support_level=145.50,
            resistance_level=162.30,
            atr=3.25,
            suggested_stop=140.62,
            reward_target=162.30,
            risk_reward_ratio=2.8,
            quantitative_score=0.72,
        )

        assert metrics.momentum_score == 0.75
        assert metrics.volume_score == 0.60
        assert metrics.relative_strength_score == 0.80
        assert metrics.risk_reward_score == 0.70
        assert metrics.rsi == 45.5
        assert metrics.macd == 0.25
        assert metrics.ema10_direction == "up"
        assert metrics.sector_etf == "XLK"
        assert metrics.quantitative_score == 0.72


class TestQuantitativeMetricsScoreValidation:
    def test_score_validation_accepts_valid_range(self):
        metrics = QuantitativeMetrics(
            momentum_score=0.0,
            volume_score=0.5,
            relative_strength_score=1.0,
            risk_reward_score=0.99,
            rsi=50.0,
            macd=0.0,
            macd_signal=0.0,
            macd_histogram=0.0,
            price_vs_sma50=0.0,
            price_vs_sma200=0.0,
            ema10_direction="flat",
            volume_ratio=1.0,
            volume_trend="flat",
            dollar_volume=1_000_000.0,
            rs_vs_spy_5d=0.0,
            rs_vs_spy_20d=0.0,
            rs_vs_spy_60d=0.0,
            rs_vs_sector=0.0,
            sector_etf="SPY",
            support_level=100.0,
            resistance_level=110.0,
            atr=2.0,
            suggested_stop=97.0,
            reward_target=110.0,
            risk_reward_ratio=3.33,
            quantitative_score=0.5,
        )

        assert metrics.momentum_score == 0.0
        assert metrics.relative_strength_score == 1.0
        assert metrics.quantitative_score == 0.5

    def test_score_validation_rejects_negative_score(self):
        with pytest.raises(ValidationError) as exc_info:
            QuantitativeMetrics(
                momentum_score=-0.1,
                volume_score=0.5,
                relative_strength_score=0.5,
                risk_reward_score=0.5,
                rsi=50.0,
                macd=0.0,
                macd_signal=0.0,
                macd_histogram=0.0,
                price_vs_sma50=0.0,
                price_vs_sma200=0.0,
                ema10_direction="flat",
                volume_ratio=1.0,
                volume_trend="flat",
                dollar_volume=1_000_000.0,
                rs_vs_spy_5d=0.0,
                rs_vs_spy_20d=0.0,
                rs_vs_spy_60d=0.0,
                rs_vs_sector=0.0,
                sector_etf="SPY",
                support_level=100.0,
                resistance_level=110.0,
                atr=2.0,
                suggested_stop=97.0,
                reward_target=110.0,
                risk_reward_ratio=3.33,
                quantitative_score=0.5,
            )
        assert "momentum_score" in str(exc_info.value)

    def test_score_validation_rejects_above_one(self):
        with pytest.raises(ValidationError) as exc_info:
            QuantitativeMetrics(
                momentum_score=0.5,
                volume_score=1.5,
                relative_strength_score=0.5,
                risk_reward_score=0.5,
                rsi=50.0,
                macd=0.0,
                macd_signal=0.0,
                macd_histogram=0.0,
                price_vs_sma50=0.0,
                price_vs_sma200=0.0,
                ema10_direction="flat",
                volume_ratio=1.0,
                volume_trend="flat",
                dollar_volume=1_000_000.0,
                rs_vs_spy_5d=0.0,
                rs_vs_spy_20d=0.0,
                rs_vs_spy_60d=0.0,
                rs_vs_sector=0.0,
                sector_etf="SPY",
                support_level=100.0,
                resistance_level=110.0,
                atr=2.0,
                suggested_stop=97.0,
                reward_target=110.0,
                risk_reward_ratio=3.33,
                quantitative_score=0.5,
            )
        assert "volume_score" in str(exc_info.value)


class TestQuantitativeMetricsSerialization:
    def test_to_dict_and_from_dict_roundtrip(self):
        original = QuantitativeMetrics(
            momentum_score=0.75,
            volume_score=0.60,
            relative_strength_score=0.80,
            risk_reward_score=0.70,
            rsi=45.5,
            macd=0.25,
            macd_signal=0.20,
            macd_histogram=0.05,
            price_vs_sma50=5.2,
            price_vs_sma200=12.3,
            ema10_direction="up",
            volume_ratio=1.8,
            volume_trend="increasing",
            dollar_volume=15_000_000.0,
            rs_vs_spy_5d=2.5,
            rs_vs_spy_20d=5.0,
            rs_vs_spy_60d=8.2,
            rs_vs_sector=3.1,
            sector_etf="XLK",
            support_level=145.50,
            resistance_level=162.30,
            atr=3.25,
            suggested_stop=140.62,
            reward_target=162.30,
            risk_reward_ratio=2.8,
            quantitative_score=0.72,
        )

        data = original.to_dict()
        restored = QuantitativeMetrics.from_dict(data)

        assert restored.momentum_score == original.momentum_score
        assert restored.volume_score == original.volume_score
        assert restored.relative_strength_score == original.relative_strength_score
        assert restored.risk_reward_score == original.risk_reward_score
        assert restored.rsi == original.rsi
        assert restored.macd == original.macd
        assert restored.ema10_direction == original.ema10_direction
        assert restored.sector_etf == original.sector_etf
        assert restored.quantitative_score == original.quantitative_score


class TestQuantitativeMetricsOptionalFields:
    def test_optional_field_handling_with_none_defaults(self):
        metrics = QuantitativeMetrics(
            momentum_score=0.5,
            volume_score=0.5,
            relative_strength_score=0.5,
            risk_reward_score=0.5,
            rsi=None,
            macd=None,
            macd_signal=None,
            macd_histogram=None,
            price_vs_sma50=None,
            price_vs_sma200=None,
            ema10_direction=None,
            volume_ratio=None,
            volume_trend=None,
            dollar_volume=None,
            rs_vs_spy_5d=None,
            rs_vs_spy_20d=None,
            rs_vs_spy_60d=None,
            rs_vs_sector=None,
            sector_etf=None,
            support_level=None,
            resistance_level=None,
            atr=None,
            suggested_stop=None,
            reward_target=None,
            risk_reward_ratio=None,
            quantitative_score=0.5,
        )

        assert metrics.rsi is None
        assert metrics.macd is None
        assert metrics.ema10_direction is None
        assert metrics.sector_etf is None
        assert metrics.momentum_score == 0.5
        assert metrics.quantitative_score == 0.5

    def test_serialization_with_none_values(self):
        original = QuantitativeMetrics(
            momentum_score=0.5,
            volume_score=0.5,
            relative_strength_score=0.5,
            risk_reward_score=0.5,
            rsi=None,
            macd=None,
            macd_signal=None,
            macd_histogram=None,
            price_vs_sma50=None,
            price_vs_sma200=None,
            ema10_direction=None,
            volume_ratio=None,
            volume_trend=None,
            dollar_volume=None,
            rs_vs_spy_5d=None,
            rs_vs_spy_20d=None,
            rs_vs_spy_60d=None,
            rs_vs_sector=None,
            sector_etf=None,
            support_level=None,
            resistance_level=None,
            atr=None,
            suggested_stop=None,
            reward_target=None,
            risk_reward_ratio=None,
            quantitative_score=0.5,
        )

        data = original.to_dict()
        restored = QuantitativeMetrics.from_dict(data)

        assert restored.rsi is None
        assert restored.ema10_direction is None
        assert restored.momentum_score == 0.5
