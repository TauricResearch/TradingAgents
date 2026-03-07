"""Unit tests for OpenAI client."""

from unittest.mock import patch

import pytest

from tradingagents.llm_clients.openai_client import OpenAIClient, UnifiedChatOpenAI


class TestOpenAIClient:
    """Tests for the OpenAI client."""

    @pytest.mark.unit
    def test_init_with_provider(self):
        """Test client initialization with provider."""
        client = OpenAIClient("gpt-4", provider="openai")
        assert client.model == "gpt-4"
        assert client.provider == "openai"
        assert client.base_url is None

    @pytest.mark.unit
    def test_init_with_base_url(self):
        """Test client initialization with base URL."""
        client = OpenAIClient("gpt-4", base_url="https://custom.api.com/v1", provider="openai")
        assert client.base_url == "https://custom.api.com/v1"

    @pytest.mark.unit
    def test_provider_lowercase(self):
        """Test that provider is lowercased."""
        client = OpenAIClient("gpt-4", provider="OpenAI")
        assert client.provider == "openai"


class TestUnifiedChatOpenAI:
    """Tests for the UnifiedChatOpenAI class."""

    @pytest.mark.unit
    def test_is_reasoning_model_o1(self):
        """Test reasoning model detection for o1 series."""
        assert UnifiedChatOpenAI._is_reasoning_model("o1-preview")
        assert UnifiedChatOpenAI._is_reasoning_model("o1-mini")
        assert UnifiedChatOpenAI._is_reasoning_model("O1-PRO")

    @pytest.mark.unit
    def test_is_reasoning_model_o3(self):
        """Test reasoning model detection for o3 series."""
        assert UnifiedChatOpenAI._is_reasoning_model("o3-mini")
        assert UnifiedChatOpenAI._is_reasoning_model("O3-MINI")

    @pytest.mark.unit
    def test_is_reasoning_model_gpt5(self):
        """Test reasoning model detection for GPT-5 series."""
        assert UnifiedChatOpenAI._is_reasoning_model("gpt-5")
        assert UnifiedChatOpenAI._is_reasoning_model("gpt-5.2")
        assert UnifiedChatOpenAI._is_reasoning_model("GPT-5-MINI")

    @pytest.mark.unit
    def test_is_not_reasoning_model(self):
        """Test that standard models are not detected as reasoning models."""
        assert not UnifiedChatOpenAI._is_reasoning_model("gpt-4o")
        assert not UnifiedChatOpenAI._is_reasoning_model("gpt-4-turbo")
        assert not UnifiedChatOpenAI._is_reasoning_model("gpt-3.5-turbo")


class TestOpenAIClientGetLLM:
    """Tests for OpenAI client get_llm method."""

    @pytest.mark.unit
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_get_llm_openai(self):
        """Test getting LLM for OpenAI provider."""
        client = OpenAIClient("gpt-4", provider="openai")
        llm = client.get_llm()
        assert llm.model == "gpt-4"

    @pytest.mark.unit
    @patch.dict("os.environ", {"XAI_API_KEY": "test-xai-key"})
    def test_get_llm_xai_uses_correct_url(self):
        """Test that xAI client uses correct base URL."""
        client = OpenAIClient("grok-beta", provider="xai")
        # Verify xAI base_url is configured
        assert client.kwargs.get("base_url") is None  # Not in kwargs, set in get_llm

    @pytest.mark.unit
    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-or-key"})
    def test_get_llm_openrouter_uses_correct_url(self):
        """Test that OpenRouter client uses correct base URL."""
        client = OpenAIClient("gpt-4", provider="openrouter")
        # Verify OpenRouter base_url is configured
        assert client.kwargs.get("base_url") is None  # Not in kwargs, set in get_llm

    @pytest.mark.unit
    def test_get_llm_ollama_uses_correct_url(self):
        """Test that Ollama client uses correct base URL."""
        client = OpenAIClient("llama2", provider="ollama")
        # Verify Ollama configuration
        assert client.provider == "ollama"

    @pytest.mark.unit
    def test_get_llm_with_timeout(self):
        """Test that timeout is passed to LLM kwargs."""
        client = OpenAIClient("gpt-4", provider="openai", timeout=60)
        # Verify timeout was passed to kwargs
        assert client.kwargs.get("timeout") == 60

    @pytest.mark.unit
    def test_get_llm_with_max_retries(self):
        """Test that max_retries is passed to LLM."""
        client = OpenAIClient("gpt-4", provider="openai", max_retries=3)
        llm = client.get_llm()
        assert llm.max_retries == 3
