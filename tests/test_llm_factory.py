"""
Comprehensive tests for LLM Factory.

Tests provider validation, model recommendations, LLM creation,
error handling, and environment variable configuration.
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal

from tradingagents.llm_factory import LLMFactory, create_llm


class TestLLMFactory:
    """Test suite for LLMFactory class."""

    def test_supported_providers(self):
        """Test that supported providers list is correct."""
        assert "openai" in LLMFactory.SUPPORTED_PROVIDERS
        assert "anthropic" in LLMFactory.SUPPORTED_PROVIDERS
        assert "google" in LLMFactory.SUPPORTED_PROVIDERS
        assert len(LLMFactory.SUPPORTED_PROVIDERS) == 3

    def test_unsupported_provider_raises_error(self):
        """Test that unsupported provider raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            LLMFactory.create_llm("unsupported_provider", "some-model")

    def test_provider_case_insensitive(self):
        """Test that provider names are case-insensitive."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("langchain_openai.ChatOpenAI") as mock_openai:
                mock_openai.return_value = Mock()

                # These should all work
                LLMFactory.create_llm("OpenAI", "gpt-4o")
                LLMFactory.create_llm("OPENAI", "gpt-4o")
                LLMFactory.create_llm("openai", "gpt-4o")

                assert mock_openai.call_count == 3


class TestOpenAILLM:
    """Test OpenAI LLM creation."""

    @patch("langchain_openai.ChatOpenAI")
    def test_create_openai_llm_basic(self, mock_openai):
        """Test basic OpenAI LLM creation."""
        mock_openai.return_value = Mock()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = LLMFactory.create_llm("openai", "gpt-4o")

            assert mock_openai.called
            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["model"] == "gpt-4o"
            assert call_kwargs["temperature"] == 1.0

    @patch("langchain_openai.ChatOpenAI")
    def test_create_openai_llm_with_temperature(self, mock_openai):
        """Test OpenAI LLM creation with custom temperature."""
        mock_openai.return_value = Mock()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            LLMFactory.create_llm("openai", "gpt-4o", temperature=0.7)

            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["temperature"] == 0.7

    @patch("langchain_openai.ChatOpenAI")
    def test_create_openai_llm_with_max_tokens(self, mock_openai):
        """Test OpenAI LLM creation with max_tokens."""
        mock_openai.return_value = Mock()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            LLMFactory.create_llm("openai", "gpt-4o", max_tokens=2048)

            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["max_tokens"] == 2048

    @patch("langchain_openai.ChatOpenAI")
    def test_create_openai_llm_with_backend_url(self, mock_openai):
        """Test OpenAI LLM creation with custom backend URL."""
        mock_openai.return_value = Mock()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            custom_url = "https://custom.openai.proxy/v1"
            LLMFactory.create_llm(
                "openai",
                "gpt-4o",
                backend_url=custom_url
            )

            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["base_url"] == custom_url

    @patch("langchain_openai.ChatOpenAI")
    def test_create_openai_llm_with_extra_kwargs(self, mock_openai):
        """Test OpenAI LLM creation with additional kwargs."""
        mock_openai.return_value = Mock()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            LLMFactory.create_llm(
                "openai",
                "gpt-4o",
                streaming=True,
                timeout=30
            )

            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["streaming"] is True
            assert call_kwargs["timeout"] == 30

    def test_create_openai_llm_missing_api_key(self):
        """Test that missing API key raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                LLMFactory.create_llm("openai", "gpt-4o")

    def test_create_openai_llm_missing_package(self):
        """Test that missing langchain-openai package raises ImportError."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"langchain_openai": None}):
                with pytest.raises(ImportError, match="langchain-openai"):
                    LLMFactory.create_llm("openai", "gpt-4o")


class TestAnthropicLLM:
    """Test Anthropic (Claude) LLM creation."""

    @patch("langchain_anthropic.ChatAnthropic")
    def test_create_anthropic_llm_basic(self, mock_anthropic):
        """Test basic Anthropic LLM creation."""
        mock_anthropic.return_value = Mock()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            llm = LLMFactory.create_llm("anthropic", "claude-3-5-sonnet-20241022")

            assert mock_anthropic.called
            call_kwargs = mock_anthropic.call_args[1]
            assert call_kwargs["model"] == "claude-3-5-sonnet-20241022"
            assert call_kwargs["temperature"] == 1.0
            assert call_kwargs["anthropic_api_key"] == "test-key"

    @patch("langchain_anthropic.ChatAnthropic")
    def test_create_anthropic_llm_with_max_tokens(self, mock_anthropic):
        """Test Anthropic LLM creation with max_tokens."""
        mock_anthropic.return_value = Mock()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            LLMFactory.create_llm("anthropic", "claude-3-5-sonnet-20241022", max_tokens=8192)

            call_kwargs = mock_anthropic.call_args[1]
            assert call_kwargs["max_tokens"] == 8192

    @patch("langchain_anthropic.ChatAnthropic")
    def test_create_anthropic_llm_default_max_tokens(self, mock_anthropic):
        """Test that Anthropic LLM gets default max_tokens if not specified."""
        mock_anthropic.return_value = Mock()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            LLMFactory.create_llm("anthropic", "claude-3-5-sonnet-20241022")

            call_kwargs = mock_anthropic.call_args[1]
            # Claude requires max_tokens, should default to 4096
            assert call_kwargs["max_tokens"] == 4096

    def test_create_anthropic_llm_missing_api_key(self):
        """Test that missing API key raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                LLMFactory.create_llm("anthropic", "claude-3-5-sonnet-20241022")

    def test_create_anthropic_llm_missing_package(self):
        """Test that missing langchain-anthropic package raises ImportError."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"langchain_anthropic": None}):
                with pytest.raises(ImportError, match="langchain-anthropic"):
                    LLMFactory.create_llm("anthropic", "claude-3-5-sonnet-20241022")


class TestGoogleLLM:
    """Test Google (Gemini) LLM creation."""

    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    def test_create_google_llm_basic(self, mock_google):
        """Test basic Google LLM creation."""
        mock_google.return_value = Mock()

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
            llm = LLMFactory.create_llm("google", "gemini-1.5-pro")

            assert mock_google.called
            call_kwargs = mock_google.call_args[1]
            assert call_kwargs["model"] == "gemini-1.5-pro"
            assert call_kwargs["temperature"] == 1.0
            assert call_kwargs["google_api_key"] == "test-key"

    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    def test_create_google_llm_with_max_tokens(self, mock_google):
        """Test Google LLM creation with max_tokens."""
        mock_google.return_value = Mock()

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
            LLMFactory.create_llm("google", "gemini-1.5-pro", max_tokens=4096)

            call_kwargs = mock_google.call_args[1]
            # Google uses max_output_tokens instead of max_tokens
            assert call_kwargs["max_output_tokens"] == 4096

    def test_create_google_llm_missing_api_key(self):
        """Test that missing API key raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
                LLMFactory.create_llm("google", "gemini-1.5-pro")

    def test_create_google_llm_missing_package(self):
        """Test that missing langchain-google-genai package raises ImportError."""
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"langchain_google_genai": None}):
                with pytest.raises(ImportError, match="langchain-google-genai"):
                    LLMFactory.create_llm("google", "gemini-1.5-pro")


class TestModelRecommendations:
    """Test model recommendation functionality."""

    def test_get_openai_recommendations(self):
        """Test getting OpenAI model recommendations."""
        models = LLMFactory.get_recommended_models("openai")

        assert "deep_thinking" in models
        assert "fast_thinking" in models
        assert "budget" in models
        assert "legacy" in models

        assert models["deep_thinking"] == "o1-preview"
        assert models["fast_thinking"] == "gpt-4o"
        assert models["budget"] == "gpt-4o-mini"

    def test_get_anthropic_recommendations(self):
        """Test getting Anthropic model recommendations."""
        models = LLMFactory.get_recommended_models("anthropic")

        assert models["deep_thinking"] == "claude-3-5-sonnet-20241022"
        assert models["fast_thinking"] == "claude-3-5-sonnet-20241022"
        assert models["budget"] == "claude-3-5-haiku-20241022"

    def test_get_google_recommendations(self):
        """Test getting Google model recommendations."""
        models = LLMFactory.get_recommended_models("google")

        assert models["deep_thinking"] == "gemini-1.5-pro"
        assert models["fast_thinking"] == "gemini-1.5-flash"
        assert models["budget"] == "gemini-1.5-flash"

    def test_get_recommendations_case_insensitive(self):
        """Test that get_recommended_models is case-insensitive."""
        models1 = LLMFactory.get_recommended_models("OpenAI")
        models2 = LLMFactory.get_recommended_models("openai")

        assert models1 == models2

    def test_get_recommendations_unknown_provider(self):
        """Test that unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown provider"):
            LLMFactory.get_recommended_models("unknown_provider")


class TestProviderValidation:
    """Test provider validation functionality."""

    def test_validate_openai_setup_complete(self):
        """Test validating complete OpenAI setup."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("langchain_openai"):
                result = LLMFactory.validate_provider_setup("openai")

                assert result["provider"] == "openai"
                assert result["valid"] is True
                assert result["api_key_set"] is True
                assert result["package_installed"] is True
                assert len(result["errors"]) == 0

    def test_validate_openai_missing_key(self):
        """Test validating OpenAI setup with missing API key."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("langchain_openai"):
                result = LLMFactory.validate_provider_setup("openai")

                assert result["valid"] is False
                assert result["api_key_set"] is False
                assert result["package_installed"] is True
                assert any("OPENAI_API_KEY" in error for error in result["errors"])

    def test_validate_openai_missing_package(self):
        """Test validating OpenAI setup with missing package."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            # Simulate ImportError by patching the import
            import sys
            original_modules = sys.modules.copy()

            # Remove the module if it exists
            if "langchain_openai" in sys.modules:
                del sys.modules["langchain_openai"]

            # Make it raise ImportError on import
            sys.modules["langchain_openai"] = None

            try:
                result = LLMFactory.validate_provider_setup("openai")

                assert result["valid"] is False
                assert result["package_installed"] is False
                assert result["api_key_set"] is True
                assert any("Package not installed" in error for error in result["errors"])
            finally:
                # Restore original modules
                sys.modules.update(original_modules)

    def test_validate_anthropic_setup_complete(self):
        """Test validating complete Anthropic setup."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("langchain_anthropic"):
                result = LLMFactory.validate_provider_setup("anthropic")

                assert result["provider"] == "anthropic"
                assert result["valid"] is True
                assert result["api_key_set"] is True
                assert result["package_installed"] is True

    def test_validate_google_setup_complete(self):
        """Test validating complete Google setup."""
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
            with patch("langchain_google_genai"):
                result = LLMFactory.validate_provider_setup("google")

                assert result["provider"] == "google"
                assert result["valid"] is True
                assert result["api_key_set"] is True
                assert result["package_installed"] is True


class TestConvenienceFunction:
    """Test the convenience create_llm function."""

    @patch("langchain_openai.ChatOpenAI")
    def test_create_llm_defaults_to_openai(self, mock_openai):
        """Test that create_llm defaults to OpenAI."""
        mock_openai.return_value = Mock()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = create_llm()

            assert mock_openai.called

    @patch("langchain_openai.ChatOpenAI")
    def test_create_llm_auto_selects_model(self, mock_openai):
        """Test that create_llm auto-selects recommended model."""
        mock_openai.return_value = Mock()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = create_llm("openai")

            call_kwargs = mock_openai.call_args[1]
            # Should use recommended deep thinking model
            assert call_kwargs["model"] == "o1-preview"

    @patch("langchain_anthropic.ChatAnthropic")
    def test_create_llm_with_specified_model(self, mock_anthropic):
        """Test create_llm with specified model."""
        mock_anthropic.return_value = Mock()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            llm = create_llm("anthropic", "claude-3-5-haiku-20241022")

            call_kwargs = mock_anthropic.call_args[1]
            assert call_kwargs["model"] == "claude-3-5-haiku-20241022"


@pytest.mark.parametrize("provider,model,env_var", [
    ("openai", "gpt-4o", "OPENAI_API_KEY"),
    ("anthropic", "claude-3-5-sonnet-20241022", "ANTHROPIC_API_KEY"),
    ("google", "gemini-1.5-pro", "GOOGLE_API_KEY"),
])
def test_all_providers_require_api_key(provider, model, env_var):
    """Parametrized test: all providers require API keys."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match=env_var):
            LLMFactory.create_llm(provider, model)


@pytest.mark.parametrize("temperature", [0.0, 0.5, 1.0, 1.5, 2.0])
def test_temperature_values(temperature):
    """Parametrized test: various temperature values."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch("tradingagents.llm_factory.ChatOpenAI") as mock_openai:
            mock_openai.return_value = Mock()

            LLMFactory.create_llm("openai", "gpt-4o", temperature=temperature)

            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["temperature"] == temperature
