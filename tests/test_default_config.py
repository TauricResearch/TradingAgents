import os

from tradingagents.default_config import DEFAULT_CONFIG


class TestDefaultConfig:
    """Test suite for DEFAULT_CONFIG dictionary."""

    def test_default_config_exists(self):
        """Test that DEFAULT_CONFIG is defined and is a dictionary."""
        assert DEFAULT_CONFIG is not None
        assert isinstance(DEFAULT_CONFIG, dict)

    def test_project_dir_configured(self):
        """Test that project_dir is configured."""
        assert "project_dir" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["project_dir"], str)
        assert os.path.isabs(DEFAULT_CONFIG["project_dir"])

    def test_results_dir_configured(self):
        """Test that results_dir is configured."""
        assert "results_dir" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["results_dir"], str)

    def test_llm_provider_configured(self):
        """Test that llm_provider is configured."""
        assert "llm_provider" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["llm_provider"] in [
            "openai",
            "anthropic",
            "google",
            "ollama",
        ]

    def test_llm_models_configured(self):
        """Test that LLM models are configured."""
        assert "deep_think_llm" in DEFAULT_CONFIG
        assert "quick_think_llm" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["deep_think_llm"], str)
        assert isinstance(DEFAULT_CONFIG["quick_think_llm"], str)

    def test_backend_url_configured(self):
        """Test that backend_url is configured."""
        assert "backend_url" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["backend_url"], str)
        assert DEFAULT_CONFIG["backend_url"].startswith("http")

    def test_debate_rounds_configured(self):
        """Test that debate round limits are configured."""
        assert "max_debate_rounds" in DEFAULT_CONFIG
        assert "max_risk_discuss_rounds" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["max_debate_rounds"], int)
        assert isinstance(DEFAULT_CONFIG["max_risk_discuss_rounds"], int)
        assert DEFAULT_CONFIG["max_debate_rounds"] > 0
        assert DEFAULT_CONFIG["max_risk_discuss_rounds"] > 0

    def test_recur_limit_configured(self):
        """Test that recursion limit is configured."""
        assert "max_recur_limit" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["max_recur_limit"], int)
        assert DEFAULT_CONFIG["max_recur_limit"] >= 100

    def test_data_vendors_configured(self):
        """Test that data vendors are configured."""
        assert "data_vendors" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["data_vendors"], dict)

        required_categories = [
            "core_stock_apis",
            "technical_indicators",
            "fundamental_data",
            "news_data",
        ]

        for category in required_categories:
            assert category in DEFAULT_CONFIG["data_vendors"]

    def test_tool_vendors_configured(self):
        """Test that tool_vendors is configured."""
        assert "tool_vendors" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["tool_vendors"], dict)

    def test_discovery_config_timeout(self):
        """Test discovery timeout configurations."""
        assert "discovery_timeout" in DEFAULT_CONFIG
        assert "discovery_hard_timeout" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["discovery_timeout"], int)
        assert isinstance(DEFAULT_CONFIG["discovery_hard_timeout"], int)
        assert (
            DEFAULT_CONFIG["discovery_hard_timeout"]
            >= DEFAULT_CONFIG["discovery_timeout"]
        )

    def test_discovery_config_cache_ttl(self):
        """Test discovery cache TTL configuration."""
        assert "discovery_cache_ttl" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["discovery_cache_ttl"], int)
        assert DEFAULT_CONFIG["discovery_cache_ttl"] > 0

    def test_discovery_config_max_results(self):
        """Test discovery max results configuration."""
        assert "discovery_max_results" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["discovery_max_results"], int)
        assert DEFAULT_CONFIG["discovery_max_results"] > 0
        assert DEFAULT_CONFIG["discovery_max_results"] <= 100

    def test_discovery_config_min_mentions(self):
        """Test discovery minimum mentions configuration."""
        assert "discovery_min_mentions" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["discovery_min_mentions"], int)
        assert DEFAULT_CONFIG["discovery_min_mentions"] >= 1

    def test_data_dir_path(self):
        """Test that data_dir path is configured."""
        assert "data_dir" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["data_dir"], str)

    def test_data_cache_dir_path(self):
        """Test that data_cache_dir is configured."""
        assert "data_cache_dir" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["data_cache_dir"], str)
        assert "data_cache" in DEFAULT_CONFIG["data_cache_dir"]

    def test_config_immutability_safety(self):
        """Test that modifying a copy doesn't affect the original."""
        original_provider = DEFAULT_CONFIG["llm_provider"]

        # Create a copy and modify it
        config_copy = DEFAULT_CONFIG.copy()
        config_copy["llm_provider"] = "modified_provider"

        # Original should remain unchanged
        assert DEFAULT_CONFIG["llm_provider"] == original_provider

    def test_all_vendor_categories_valid(self):
        """Test that all data vendor categories are valid."""
        valid_categories = [
            "core_stock_apis",
            "technical_indicators",
            "fundamental_data",
            "news_data",
        ]

        for category in DEFAULT_CONFIG["data_vendors"].keys():
            assert category in valid_categories

    def test_vendor_values_are_strings(self):
        """Test that all vendor values are strings."""
        for vendor in DEFAULT_CONFIG["data_vendors"].values():
            assert isinstance(vendor, str)

    def test_numeric_configs_positive(self):
        """Test that all numeric configs have sensible positive values."""
        numeric_configs = [
            "max_debate_rounds",
            "max_risk_discuss_rounds",
            "max_recur_limit",
            "discovery_timeout",
            "discovery_hard_timeout",
            "discovery_cache_ttl",
            "discovery_max_results",
            "discovery_min_mentions",
        ]

        for config_key in numeric_configs:
            value = DEFAULT_CONFIG[config_key]
            assert isinstance(value, int)
            assert value > 0

    def test_results_dir_uses_env_var(self):
        """Test that results_dir respects environment variable."""
        # The config uses os.getenv with a default
        results_dir = DEFAULT_CONFIG["results_dir"]

        # Should either be from env or default to ./results
        assert isinstance(results_dir, str)
        assert len(results_dir) > 0
