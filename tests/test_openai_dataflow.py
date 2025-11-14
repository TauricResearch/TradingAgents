"""
Tests for openai dataflow module to ensure compatibility with different LLM providers.
This test reproduces issue #275 where Gemini and OpenRouter fail with openai vendor.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from tradingagents.dataflows.openai import (
    get_stock_news_openai,
    get_global_news_openai,
    get_fundamentals_openai
)


class TestOpenAIDataflowCompatibility:
    """Test that openai dataflow functions work with different LLM providers."""
    
    @pytest.fixture
    def mock_config_openai(self):
        """Mock config for OpenAI provider."""
        return {
            "backend_url": "https://api.openai.com/v1",
            "quick_think_llm": "gpt-4o-mini",
            "llm_provider": "openai"
        }
    
    @pytest.fixture
    def mock_config_gemini(self):
        """Mock config for Google Gemini provider."""
        return {
            "backend_url": "https://generativelanguage.googleapis.com/v1",
            "quick_think_llm": "gemini-2.0-flash",
            "llm_provider": "google"
        }
    
    @pytest.fixture
    def mock_config_openrouter(self):
        """Mock config for OpenRouter provider."""
        return {
            "backend_url": "https://openrouter.ai/api/v1",
            "quick_think_llm": "deepseek/deepseek-chat-v3-0324:free",
            "llm_provider": "openrouter"
        }
    
    @patch('tradingagents.dataflows.openai.get_config')
    @patch('tradingagents.dataflows.openai.OpenAI')
    def test_get_global_news_with_openai(self, mock_openai_class, mock_get_config, mock_config_openai):
        """Test get_global_news_openai works with OpenAI provider."""
        mock_get_config.return_value = mock_config_openai
        
        # Mock the OpenAI client and response
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        # Mock chat completion response (standard API)
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Test news content"
        mock_client.chat.completions.create.return_value = mock_response
        
        # Call the function
        result = get_global_news_openai("2024-11-09", 7, 5)
        
        # Verify it was called
        assert mock_client.chat.completions.create.called
        assert result == "Test news content"
    
    @patch('tradingagents.dataflows.openai.get_config')
    @patch('tradingagents.dataflows.openai.OpenAI')
    def test_get_global_news_with_gemini(self, mock_openai_class, mock_get_config, mock_config_gemini):
        """Test get_global_news_openai works with Gemini provider (via OpenAI-compatible API)."""
        mock_get_config.return_value = mock_config_gemini
        
        # Mock the OpenAI client and response
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        # Mock chat completion response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Test Gemini news content"
        mock_client.chat.completions.create.return_value = mock_response
        
        # Call the function - should not raise an error
        result = get_global_news_openai("2024-11-09", 7, 5)
        
        # Verify it was called with standard chat completion API
        assert mock_client.chat.completions.create.called
        assert result == "Test Gemini news content"
    
    @patch('tradingagents.dataflows.openai.get_config')
    @patch('tradingagents.dataflows.openai.OpenAI')
    def test_get_global_news_with_openrouter(self, mock_openai_class, mock_get_config, mock_config_openrouter):
        """Test get_global_news_openai works with OpenRouter provider."""
        mock_get_config.return_value = mock_config_openrouter
        
        # Mock the OpenAI client and response
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        # Mock chat completion response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Test OpenRouter news content"
        mock_client.chat.completions.create.return_value = mock_response
        
        # Call the function - should not raise an error
        result = get_global_news_openai("2024-11-09", 7, 5)
        
        # Verify it was called with standard chat completion API
        assert mock_client.chat.completions.create.called
        assert result == "Test OpenRouter news content"
    
    @patch('tradingagents.dataflows.openai.get_config')
    @patch('tradingagents.dataflows.openai.OpenAI')
    def test_get_fundamentals_with_different_providers(self, mock_openai_class, mock_get_config, mock_config_gemini):
        """Test get_fundamentals_openai works with different providers."""
        mock_get_config.return_value = mock_config_gemini
        
        # Mock the OpenAI client and response
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        # Mock chat completion response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Test fundamentals data"
        mock_client.chat.completions.create.return_value = mock_response
        
        # Call the function
        result = get_fundamentals_openai("AAPL", "2024-11-09")
        
        # Verify it was called
        assert mock_client.chat.completions.create.called
        assert result == "Test fundamentals data"

