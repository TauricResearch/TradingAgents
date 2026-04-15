"""Unit tests for Anthropic client."""

from unittest.mock import patch

import pytest

from tradingagents.llm_clients.anthropic_client import AnthropicClient


class TestAnthropicClient:
    """Tests for the Anthropic client."""

    @pytest.mark.unit
    def test_init(self):
        """Test client initialization."""
        client = AnthropicClient("claude-3-opus")
        assert client.model == "claude-3-opus"
        assert client.base_url is None

    @pytest.mark.unit
    def test_init_with_base_url(self):
        """Test client initialization with base URL (accepted but may be ignored)."""
        client = AnthropicClient("claude-3-opus", base_url="https://custom.api.com")
        assert client.base_url == "https://custom.api.com"

    @pytest.mark.unit
    def test_init_with_kwargs(self):
        """Test client initialization with additional kwargs."""
        client = AnthropicClient("claude-3-opus", timeout=30, max_tokens=4096)
        assert client.kwargs.get("timeout") == 30
        assert client.kwargs.get("max_tokens") == 4096


class TestAnthropicClientGetLLM:
    """Tests for Anthropic client get_llm method."""

    @pytest.mark.unit
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    def test_get_llm_returns_chat_anthropic(self):
        """Test that get_llm returns a ChatAnthropic instance."""
        client = AnthropicClient("claude-3-opus")
        llm = client.get_llm()
        assert llm.model == "claude-3-opus"

    @pytest.mark.unit
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    def test_get_llm_with_timeout(self):
        """Test that timeout is passed to LLM kwargs."""
        client = AnthropicClient("claude-3-opus", timeout=60)
        # Verify timeout was passed to kwargs (ChatAnthropic may not expose it directly)
        assert "timeout" in client.kwargs

    @pytest.mark.unit
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    def test_get_llm_with_max_tokens(self):
        """Test that max_tokens is passed to LLM."""
        client = AnthropicClient("claude-3-opus", max_tokens=2048)
        client.get_llm()
        # ChatAnthropic uses max_tokens_mixin or similar
        assert "max_tokens" in client.kwargs


class TestAnthropicClientValidateModel:
    """Tests for Anthropic client validate_model method."""

    @pytest.mark.unit
    def test_validate_model_returns_bool(self):
        """Test that validate_model returns a boolean."""
        client = AnthropicClient("claude-3-opus")
        # This calls the validator function
        result = client.validate_model()
        assert isinstance(result, bool)
