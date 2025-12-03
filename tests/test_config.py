import pytest
import os
from unittest.mock import patch

from tradingagents.config import (
    TradingAgentsSettings,
    DataVendorsConfig,
    get_settings,
    reset_settings,
    update_settings,
)


class TestDataVendorsConfig:
    def test_default_values(self):
        config = DataVendorsConfig()
        assert config.core_stock_apis == "yfinance"
        assert config.technical_indicators == "yfinance"
        assert config.fundamental_data == "alpha_vantage"
        assert config.news_data == "alpha_vantage"

    def test_custom_values(self):
        config = DataVendorsConfig(core_stock_apis="local", news_data="openai")
        assert config.core_stock_apis == "local"
        assert config.news_data == "openai"


class TestTradingAgentsSettings:
    def setup_method(self):
        reset_settings()

    def teardown_method(self):
        reset_settings()

    def test_default_values(self):
        settings = TradingAgentsSettings()
        assert settings.llm_provider == "openai"
        assert settings.log_level == "INFO"
        assert settings.max_debate_rounds == 2

    def test_log_level_validation(self):
        settings = TradingAgentsSettings(log_level="debug")
        assert settings.log_level == "DEBUG"

        settings = TradingAgentsSettings(log_level="WARNING")
        assert settings.log_level == "WARNING"

    def test_log_level_invalid(self):
        with pytest.raises(ValueError, match="Invalid log level"):
            TradingAgentsSettings(log_level="INVALID")

    def test_llm_provider_validation(self):
        settings = TradingAgentsSettings(llm_provider="OPENAI")
        assert settings.llm_provider == "openai"

        settings = TradingAgentsSettings(llm_provider="Anthropic")
        assert settings.llm_provider == "anthropic"

    def test_llm_provider_invalid(self):
        with pytest.raises(ValueError, match="Invalid LLM provider"):
            TradingAgentsSettings(llm_provider="invalid_provider")

    def test_to_dict(self):
        settings = TradingAgentsSettings()
        result = settings.to_dict()

        assert isinstance(result, dict)
        assert "llm_provider" in result
        assert "data_vendors" in result
        assert isinstance(result["data_vendors"], dict)

    def test_get_api_key_returns_value(self):
        settings = TradingAgentsSettings(openai_api_key="test-key")
        assert settings.get_api_key("openai") == "test-key"

    def test_get_api_key_returns_none_when_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = TradingAgentsSettings()
            settings.openai_api_key = None
            assert settings.get_api_key("openai") is None

    def test_require_api_key_raises_when_not_set(self):
        settings = TradingAgentsSettings()
        settings.brave_api_key = None
        with pytest.raises(ValueError, match="brave API key not configured"):
            settings.require_api_key("brave")

    def test_require_api_key_returns_value(self):
        settings = TradingAgentsSettings(tavily_api_key="tavily-test")
        assert settings.require_api_key("tavily") == "tavily-test"

    def test_max_debate_rounds_bounds(self):
        settings = TradingAgentsSettings(max_debate_rounds=5)
        assert settings.max_debate_rounds == 5

        with pytest.raises(ValueError):
            TradingAgentsSettings(max_debate_rounds=0)

        with pytest.raises(ValueError):
            TradingAgentsSettings(max_debate_rounds=20)


class TestConfigFunctions:
    def setup_method(self):
        reset_settings()

    def teardown_method(self):
        reset_settings()

    def test_get_settings_returns_singleton(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_reset_settings_clears_singleton(self):
        s1 = get_settings()
        reset_settings()
        s2 = get_settings()
        assert s1 is not s2

    def test_update_settings_modifies_values(self):
        original = get_settings()
        assert original.max_debate_rounds == 2

        update_settings(max_debate_rounds=5)
        updated = get_settings()
        assert updated.max_debate_rounds == 5

    def test_update_settings_preserves_other_values(self):
        original = get_settings()
        original_provider = original.llm_provider

        update_settings(max_debate_rounds=5)
        updated = get_settings()
        assert updated.llm_provider == original_provider


class TestDataflowConfigCompat:
    def setup_method(self):
        reset_settings()

    def teardown_method(self):
        reset_settings()

    def test_get_config_returns_dict(self):
        from tradingagents.dataflows.config import get_config

        config = get_config()
        assert isinstance(config, dict)
        assert "llm_provider" in config
        assert "data_vendors" in config

    def test_set_config_updates_central_settings(self):
        from tradingagents.dataflows.config import get_config, set_config

        set_config({"max_debate_rounds": 4})
        config = get_config()
        assert config["max_debate_rounds"] == 4

    def test_get_config_returns_copy(self):
        from tradingagents.dataflows.config import get_config

        c1 = get_config()
        c2 = get_config()
        assert c1 == c2
        c1["llm_provider"] = "modified"
        c3 = get_config()
        assert c3["llm_provider"] != "modified"
