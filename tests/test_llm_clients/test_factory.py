"""Unit tests for LLM client factory."""


import pytest

from tradingagents.llm_clients.anthropic_client import AnthropicClient
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.google_client import GoogleClient
from tradingagents.llm_clients.openai_client import OpenAIClient


class TestCreateLLMClient:
    """Tests for the LLM client factory function."""

    @pytest.mark.unit
    def test_create_openai_client(self):
        """Test creating an OpenAI client."""
        client = create_llm_client("openai", "gpt-4")
        assert isinstance(client, OpenAIClient)
        assert client.model == "gpt-4"
        assert client.provider == "openai"

    @pytest.mark.unit
    def test_create_openai_client_case_insensitive(self):
        """Test that provider names are case insensitive."""
        client = create_llm_client("OpenAI", "gpt-4o")
        assert isinstance(client, OpenAIClient)
        assert client.provider == "openai"

    @pytest.mark.unit
    def test_create_anthropic_client(self):
        """Test creating an Anthropic client."""
        client = create_llm_client("anthropic", "claude-3-opus")
        assert isinstance(client, AnthropicClient)
        assert client.model == "claude-3-opus"

    @pytest.mark.unit
    def test_create_google_client(self):
        """Test creating a Google client."""
        client = create_llm_client("google", "gemini-pro")
        assert isinstance(client, GoogleClient)
        assert client.model == "gemini-pro"

    @pytest.mark.unit
    def test_create_xai_client(self):
        """Test creating an xAI client (uses OpenAI-compatible API)."""
        client = create_llm_client("xai", "grok-beta")
        assert isinstance(client, OpenAIClient)
        assert client.provider == "xai"

    @pytest.mark.unit
    def test_create_ollama_client(self):
        """Test creating an Ollama client."""
        client = create_llm_client("ollama", "llama2")
        assert isinstance(client, OpenAIClient)
        assert client.provider == "ollama"

    @pytest.mark.unit
    def test_create_openrouter_client(self):
        """Test creating an OpenRouter client."""
        client = create_llm_client("openrouter", "gpt-4")
        assert isinstance(client, OpenAIClient)
        assert client.provider == "openrouter"

    @pytest.mark.unit
    def test_unsupported_provider_raises(self):
        """Test that unsupported provider raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            create_llm_client("unknown_provider", "model-name")

    @pytest.mark.unit
    def test_create_client_with_base_url(self):
        """Test creating a client with custom base URL."""
        client = create_llm_client("openai", "gpt-4", base_url="https://custom.api.com/v1")
        assert client.base_url == "https://custom.api.com/v1"

    @pytest.mark.unit
    def test_create_client_with_kwargs(self):
        """Test creating a client with additional kwargs."""
        client = create_llm_client("openai", "gpt-4", timeout=30, max_retries=5)
        assert client.kwargs.get("timeout") == 30
        assert client.kwargs.get("max_retries") == 5
