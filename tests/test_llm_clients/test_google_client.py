"""Unit tests for Google client."""

from unittest.mock import patch

import pytest

from tradingagents.llm_clients.google_client import GoogleClient


class TestGoogleClient:
    """Tests for the Google client."""

    @pytest.mark.unit
    def test_init(self):
        """Test client initialization."""
        client = GoogleClient("gemini-pro")
        assert client.model == "gemini-pro"
        assert client.base_url is None

    @pytest.mark.unit
    def test_init_with_kwargs(self):
        """Test client initialization with additional kwargs."""
        client = GoogleClient("gemini-pro", timeout=30)
        assert client.kwargs.get("timeout") == 30


class TestGoogleClientGetLLM:
    """Tests for Google client get_llm method."""

    @pytest.mark.unit
    @patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"})
    def test_get_llm_returns_chat_google(self):
        """Test that get_llm returns a ChatGoogleGenerativeAI instance."""
        client = GoogleClient("gemini-pro")
        llm = client.get_llm()
        assert llm.model == "gemini-pro"

    @pytest.mark.unit
    @patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"})
    def test_get_llm_with_timeout(self):
        """Test that timeout is passed to LLM."""
        client = GoogleClient("gemini-pro", timeout=60)
        llm = client.get_llm()
        assert llm.timeout == 60

    @pytest.mark.unit
    @patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"})
    def test_get_llm_gemini_3_pro_thinking_level(self):
        """Test thinking level for Gemini 3 Pro models."""
        client = GoogleClient("gemini-3-pro", thinking_level="high")
        client.get_llm()
        # Gemini 3 Pro should get thinking_level directly
        assert "thinking_level" in client.kwargs

    @pytest.mark.unit
    @patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"})
    def test_get_llm_gemini_3_pro_minimal_to_low(self):
        """Test that 'minimal' thinking level maps to 'low' for Gemini 3 Pro."""
        client = GoogleClient("gemini-3-pro", thinking_level="minimal")
        llm = client.get_llm()
        # Pro models don't support 'minimal', should be mapped to 'low'
        assert llm.thinking_level == "low"

    @pytest.mark.unit
    @patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"})
    def test_get_llm_gemini_3_flash_thinking_level(self):
        """Test thinking level for Gemini 3 Flash models."""
        client = GoogleClient("gemini-3-flash", thinking_level="medium")
        llm = client.get_llm()
        # Gemini 3 Flash supports minimal, low, medium, high
        assert llm.thinking_level == "medium"


class TestNormalizedChatGoogleGenerativeAI:
    """Tests for the normalized Google Generative AI class."""

    @pytest.mark.unit
    def test_normalize_string_content(self):
        """Test that string content is left unchanged."""
        # This is a static method test via the class
        # The _normalize_content method handles list content
        # Actual test would need a mock response

    @pytest.mark.unit
    def test_normalize_list_content(self):
        """Test that list content is normalized to string."""
        # This tests the normalization logic for Gemini 3 responses
        # that return content as list of dicts
        # Actual test would need integration with the class


class TestGoogleClientValidateModel:
    """Tests for Google client validate_model method."""

    @pytest.mark.unit
    def test_validate_model_returns_bool(self):
        """Test that validate_model returns a boolean."""
        client = GoogleClient("gemini-pro")
        result = client.validate_model()
        assert isinstance(result, bool)
