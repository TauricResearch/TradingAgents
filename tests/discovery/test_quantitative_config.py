import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from tradingagents.config import (
    QuantitativeWeightsConfig,
    TradingAgentsSettings,
    get_settings,
    reset_settings,
)


class TestQuantitativeWeightsConfigDefaults:
    def test_default_weight_values_are_set_correctly(self):
        config = QuantitativeWeightsConfig()

        assert config.news_sentiment_weight == 0.50
        assert config.quantitative_weight == 0.50
        assert config.momentum_weight == 0.30
        assert config.volume_weight == 0.25
        assert config.relative_strength_weight == 0.25
        assert config.risk_reward_weight == 0.20


class TestQuantitativeWeightsConfigValidation:
    def test_top_level_weights_sum_to_one(self):
        config = QuantitativeWeightsConfig(
            news_sentiment_weight=0.60,
            quantitative_weight=0.40,
        )
        assert (
            config.news_sentiment_weight + config.quantitative_weight
            == pytest.approx(1.0)
        )

    def test_sub_weights_sum_to_one(self):
        config = QuantitativeWeightsConfig()
        sub_weights_sum = (
            config.momentum_weight
            + config.volume_weight
            + config.relative_strength_weight
            + config.risk_reward_weight
        )
        assert sub_weights_sum == pytest.approx(1.0)

    def test_top_level_weights_validation_rejects_invalid_sum(self):
        with pytest.raises(ValidationError) as exc_info:
            QuantitativeWeightsConfig(
                news_sentiment_weight=0.60,
                quantitative_weight=0.60,
            )
        assert "sum to 1.0" in str(exc_info.value).lower()

    def test_sub_weights_validation_rejects_invalid_sum(self):
        with pytest.raises(ValidationError) as exc_info:
            QuantitativeWeightsConfig(
                momentum_weight=0.50,
                volume_weight=0.50,
                relative_strength_weight=0.50,
                risk_reward_weight=0.50,
            )
        assert "sum to 1.0" in str(exc_info.value).lower()


class TestQuantitativeWeightsConfigEnvOverride:
    def setup_method(self):
        reset_settings()

    def teardown_method(self):
        reset_settings()

    def test_environment_variable_override_functionality(self):
        env_vars = {
            "TRADINGAGENTS_QUANTITATIVE_WEIGHTS__NEWS_SENTIMENT_WEIGHT": "0.70",
            "TRADINGAGENTS_QUANTITATIVE_WEIGHTS__QUANTITATIVE_WEIGHT": "0.30",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            reset_settings()
            settings = get_settings()

            assert settings.quantitative_weights.news_sentiment_weight == pytest.approx(
                0.70
            )
            assert settings.quantitative_weights.quantitative_weight == pytest.approx(
                0.30
            )


class TestQuantitativeSettingsIntegration:
    def setup_method(self):
        reset_settings()

    def teardown_method(self):
        reset_settings()

    def test_quantitative_settings_in_trading_agents_settings(self):
        settings = TradingAgentsSettings()

        assert hasattr(settings, "quantitative_weights")
        assert isinstance(settings.quantitative_weights, QuantitativeWeightsConfig)
        assert hasattr(settings, "quantitative_max_stocks")
        assert hasattr(settings, "quantitative_cache_ttl_intraday")
        assert hasattr(settings, "quantitative_cache_ttl_relative_strength")
        assert hasattr(settings, "min_dollar_volume")

    def test_quantitative_settings_default_values(self):
        settings = TradingAgentsSettings()

        assert settings.quantitative_max_stocks == 50
        assert settings.quantitative_cache_ttl_intraday == 1
        assert settings.quantitative_cache_ttl_relative_strength == 4
        assert settings.min_dollar_volume == 1_000_000.0

    def test_quantitative_max_stocks_bounds(self):
        settings = TradingAgentsSettings(quantitative_max_stocks=75)
        assert settings.quantitative_max_stocks == 75

        with pytest.raises(ValidationError):
            TradingAgentsSettings(quantitative_max_stocks=5)

        with pytest.raises(ValidationError):
            TradingAgentsSettings(quantitative_max_stocks=150)
