"""Tests for CLI utilities, specifically OpenRouter model configuration."""

import pytest
from cli.utils import SHALLOW_AGENT_OPTIONS, DEEP_AGENT_OPTIONS


class TestOpenRouterModels:
    """Test suite for OpenRouter model configuration."""

    def test_shallow_thinking_openrouter_models_count(self):
        """Verify OpenRouter shallow thinking models list has expected entries."""
        openrouter_models = SHALLOW_AGENT_OPTIONS.get("openrouter", [])

        # Should have at least 12 models (top 10 + 2 free models)
        assert len(openrouter_models) >= 12, (
            f"Expected at least 12 models, got {len(openrouter_models)}"
        )

    def test_deep_thinking_openrouter_models_count(self):
        """Verify OpenRouter deep thinking models list has expected entries."""
        openrouter_models = DEEP_AGENT_OPTIONS.get("openrouter", [])

        # Should have at least 12 models (top 10 + 2 free models)
        assert len(openrouter_models) >= 12, (
            f"Expected at least 12 models, got {len(openrouter_models)}"
        )

    def test_openrouter_models_have_required_format(self):
        """Verify all OpenRouter models follow the expected format."""
        for model_list in [
            SHALLOW_AGENT_OPTIONS.get("openrouter", []),
            DEEP_AGENT_OPTIONS.get("openrouter", []),
        ]:
            for display_name, model_id in model_list:
                # Display name should be a string
                assert isinstance(display_name, str), (
                    f"Display name must be string, got {type(display_name)}"
                )
                assert len(display_name) > 0, "Display name cannot be empty"

                # Model ID should be a string with provider/model format
                assert isinstance(model_id, str), (
                    f"Model ID must be string, got {type(model_id)}"
                )
                assert "/" in model_id, (
                    f"Model ID {model_id} should contain provider prefix"
                )

    def test_top_models_included(self):
        """Verify top ranked models from OpenRouter are included."""
        # Key models that should be present (based on OpenRouter rankings)
        expected_models = [
            "moonshotai/kimi-k2.5-0127",  # #1 ranked
            "anthropic/claude-4.5-opus-20251124",  # Top Claude
            "anthropic/claude-4.5-sonnet-20250929",  # Popular Claude
            "google/gemini-3-flash-preview-20251217",  # Top Gemini
            "deepseek/deepseek-v3.2-20251201",  # Popular open source
            "x-ai/grok-4.1-fast",  # xAI model
        ]

        all_models = []
        for options in [SHALLOW_AGENT_OPTIONS, DEEP_AGENT_OPTIONS]:
            all_models.extend(
                [model_id for _, model_id in options.get("openrouter", [])]
            )

        for expected in expected_models:
            assert expected in all_models, (
                f"Expected model {expected} not found in configuration"
            )

    def test_free_models_still_available(self):
        """Verify free models are still included."""
        free_models = [
            "nvidia/nemotron-3-nano-30b-a3b:free",
            "z-ai/glm-4.5-air:free",
        ]

        all_models = []
        for options in [SHALLOW_AGENT_OPTIONS, DEEP_AGENT_OPTIONS]:
            all_models.extend(
                [model_id for _, model_id in options.get("openrouter", [])]
            )

        for free_model in free_models:
            assert free_model in all_models, (
                f"Free model {free_model} should be preserved"
            )

    def test_no_duplicate_model_ids(self):
        """Verify no duplicate model IDs exist in OpenRouter lists."""
        for options in [SHALLOW_AGENT_OPTIONS, DEEP_AGENT_OPTIONS]:
            model_ids = [model_id for _, model_id in options.get("openrouter", [])]
            assert len(model_ids) == len(set(model_ids)), "Duplicate model IDs found"

    def test_all_providers_have_models(self):
        """Verify all supported providers have model entries."""
        expected_providers = [
            "openai",
            "anthropic",
            "google",
            "xai",
            "openrouter",
            "ollama",
        ]

        for provider in expected_providers:
            assert provider in SHALLOW_AGENT_OPTIONS, (
                f"Provider {provider} missing from shallow options"
            )
            assert len(SHALLOW_AGENT_OPTIONS[provider]) > 0, (
                f"Provider {provider} has no shallow models"
            )

            assert provider in DEEP_AGENT_OPTIONS, (
                f"Provider {provider} missing from deep options"
            )
            assert len(DEEP_AGENT_OPTIONS[provider]) > 0, (
                f"Provider {provider} has no deep models"
            )

    def test_model_consistency_between_lists(self):
        """Verify common models appear in both shallow and deep lists where applicable."""
        shallow_models = set(
            model_id for _, model_id in SHALLOW_AGENT_OPTIONS.get("openrouter", [])
        )
        deep_models = set(
            model_id for _, model_id in DEEP_AGENT_OPTIONS.get("openrouter", [])
        )

        # Free models should be in both lists
        free_models = {"nvidia/nemotron-3-nano-30b-a3b:free", "z-ai/glm-4.5-air:free"}
        for free_model in free_models:
            assert free_model in shallow_models, (
                f"Free model {free_model} should be in shallow list"
            )
            assert free_model in deep_models, (
                f"Free model {free_model} should be in deep list"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
