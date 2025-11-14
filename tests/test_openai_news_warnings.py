"""
Tests for OpenAI news dataflow functions to ensure proper warnings about hallucination risks.

Issue #274: OpenAI is hallucinating and provides outdated news.
The OpenAI vendor for news retrieval doesn't have reliable real-time web search access,
so it may generate fake or outdated news based on its training data.
"""

import pytest
import warnings
from unittest.mock import Mock, patch
from tradingagents.dataflows.openai import (
    get_global_news_openai,
    get_stock_news_openai,
    get_fundamentals_openai,
)


class TestOpenAINewsWarnings:
    """Test that OpenAI news functions emit appropriate warnings about hallucination risks."""

    @patch("tradingagents.dataflows.openai.OpenAI")
    @patch("tradingagents.dataflows.openai.get_config")
    def test_get_global_news_emits_warning(self, mock_get_config, mock_openai_class):
        """Test that get_global_news_openai emits a warning about potential hallucination."""
        # Setup mocks
        mock_config = {
            "backend_url": "https://api.openai.com/v1",
            "quick_think_llm": "gpt-4o-mini",
        }
        mock_get_config.return_value = mock_config

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Mock the response
        mock_response = Mock()
        mock_response.output = [None, Mock(content=[Mock(text="Fake news content")])]
        mock_client.responses.create.return_value = mock_response

        # Test that a warning is emitted
        with pytest.warns(UserWarning, match="may hallucinate|outdated|unreliable"):
            result = get_global_news_openai("2024-11-14", look_back_days=7, limit=5)

        assert result is not None

    @patch("tradingagents.dataflows.openai.OpenAI")
    @patch("tradingagents.dataflows.openai.get_config")
    def test_get_stock_news_emits_warning(self, mock_get_config, mock_openai_class):
        """Test that get_stock_news_openai emits a warning about potential hallucination."""
        # Setup mocks
        mock_config = {
            "backend_url": "https://api.openai.com/v1",
            "quick_think_llm": "gpt-4o-mini",
        }
        mock_get_config.return_value = mock_config

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Mock the response
        mock_response = Mock()
        mock_response.output = [None, Mock(content=[Mock(text="Fake stock news")])]
        mock_client.responses.create.return_value = mock_response

        # Test that a warning is emitted
        with pytest.warns(UserWarning, match="may hallucinate|outdated|unreliable"):
            result = get_stock_news_openai("NVDA", "2024-11-01", "2024-11-14")

        assert result is not None

    @patch("tradingagents.dataflows.openai.OpenAI")
    @patch("tradingagents.dataflows.openai.get_config")
    def test_get_fundamentals_emits_warning(self, mock_get_config, mock_openai_class):
        """Test that get_fundamentals_openai emits a warning about potential hallucination."""
        # Setup mocks
        mock_config = {
            "backend_url": "https://api.openai.com/v1",
            "quick_think_llm": "gpt-4o-mini",
        }
        mock_get_config.return_value = mock_config

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Mock the response
        mock_response = Mock()
        mock_response.output = [None, Mock(content=[Mock(text="Fake fundamentals")])]
        mock_client.responses.create.return_value = mock_response

        # Test that a warning is emitted
        with pytest.warns(UserWarning, match="may hallucinate|outdated|unreliable"):
            result = get_fundamentals_openai("NVDA", "2024-11-14")

        assert result is not None

    def test_warning_message_content(self):
        """Test that warning messages contain helpful information about alternatives."""
        # This test verifies the warning message suggests using alternative vendors
        with patch("tradingagents.dataflows.openai.OpenAI"), \
             patch("tradingagents.dataflows.openai.get_config") as mock_get_config:
            
            mock_get_config.return_value = {
                "backend_url": "https://api.openai.com/v1",
                "quick_think_llm": "gpt-4o-mini",
            }

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                
                try:
                    get_global_news_openai("2024-11-14")
                except Exception:
                    pass  # We're only testing the warning, not the full execution

                # Check that at least one warning was issued
                assert len(w) > 0
                
                # Check that the warning mentions alternatives
                warning_text = str(w[0].message).lower()
                assert any(keyword in warning_text for keyword in [
                    "alpha_vantage", "google", "local", "alternative", "vendor"
                ])

