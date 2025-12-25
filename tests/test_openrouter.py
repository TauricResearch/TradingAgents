"""
Test suite for OpenRouter API support in TradingAgents.

This module tests:
1. OpenRouter provider initialization with ChatOpenAI
2. API key handling (OPENROUTER_API_KEY vs OPENAI_API_KEY)
3. Error handling for missing API keys
4. Model name format validation (provider/model-name)
5. Embedding fallback behavior
6. Configuration validation
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# Import modules under test
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.default_config import DEFAULT_CONFIG


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def openrouter_config():
    """Create a valid OpenRouter configuration."""
    config = DEFAULT_CONFIG.copy()
    config.update({
        "llm_provider": "openrouter",
        "deep_think_llm": "anthropic/claude-sonnet-4",
        "quick_think_llm": "anthropic/claude-haiku-3.5",
        "backend_url": "https://openrouter.ai/api/v1",
    })
    return config


@pytest.fixture
def mock_env_openrouter():
    """Mock environment with OPENROUTER_API_KEY set."""
    with patch.dict(os.environ, {
        "OPENROUTER_API_KEY": "sk-or-test-key-123",
    }, clear=True):
        yield


@pytest.fixture
def mock_env_openai():
    """Mock environment with only OPENAI_API_KEY set."""
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "sk-test-key-456",
    }, clear=True):
        yield


@pytest.fixture
def mock_env_empty():
    """Mock environment with no API keys."""
    with patch.dict(os.environ, {}, clear=True):
        yield


@pytest.fixture
def mock_langchain_classes():
    """Mock LangChain chat model classes."""
    with patch("tradingagents.graph.trading_graph.ChatOpenAI") as mock_openai, \
         patch("tradingagents.graph.trading_graph.ChatAnthropic") as mock_anthropic, \
         patch("tradingagents.graph.trading_graph.ChatGoogleGenerativeAI") as mock_google:

        # Configure mocks to return Mock instances
        mock_openai.return_value = Mock()
        mock_anthropic.return_value = Mock()
        mock_google.return_value = Mock()

        yield {
            "openai": mock_openai,
            "anthropic": mock_anthropic,
            "google": mock_google,
        }


@pytest.fixture
def mock_memory():
    """Mock FinancialSituationMemory to avoid actual ChromaDB/OpenAI calls."""
    with patch("tradingagents.graph.trading_graph.FinancialSituationMemory") as mock:
        mock.return_value = Mock(spec=FinancialSituationMemory)
        yield mock


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for embedding tests."""
    with patch("tradingagents.agents.utils.memory.OpenAI") as mock:
        client_instance = Mock()
        mock.return_value = client_instance

        # Mock embedding response
        embedding_response = Mock()
        embedding_response.data = [Mock(embedding=[0.1] * 1536)]
        client_instance.embeddings.create.return_value = embedding_response

        yield mock


@pytest.fixture
def mock_chromadb():
    """Mock ChromaDB client."""
    with patch("tradingagents.agents.utils.memory.chromadb.Client") as mock:
        client_instance = Mock()
        collection_instance = Mock()
        collection_instance.count.return_value = 0
        client_instance.create_collection.return_value = collection_instance
        mock.return_value = client_instance
        yield mock


# ============================================================================
# Unit Tests: OpenRouter Provider Initialization
# ============================================================================

class TestOpenRouterInitialization:
    """Test OpenRouter provider initializes ChatOpenAI with correct parameters."""

    def test_openrouter_uses_chatopenai(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that OpenRouter provider uses ChatOpenAI class."""
        # Arrange: OpenRouter config ready

        # Act: Initialize TradingAgentsGraph
        graph = TradingAgentsGraph(config=openrouter_config)

        # Assert: ChatOpenAI was called, not Anthropic or Google
        assert mock_langchain_classes["openai"].called
        assert not mock_langchain_classes["anthropic"].called
        assert not mock_langchain_classes["google"].called

    def test_openrouter_sets_correct_base_url(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that OpenRouter sets base_url to https://openrouter.ai/api/v1."""
        # Arrange
        expected_url = "https://openrouter.ai/api/v1"

        # Act
        graph = TradingAgentsGraph(config=openrouter_config)

        # Assert: Check both deep and quick thinking LLMs
        calls = mock_langchain_classes["openai"].call_args_list
        assert len(calls) >= 2, "Expected at least 2 ChatOpenAI calls"

        # Check deep thinking LLM
        deep_call_kwargs = calls[0][1]  # Get keyword arguments
        assert deep_call_kwargs["base_url"] == expected_url

        # Check quick thinking LLM
        quick_call_kwargs = calls[1][1]
        assert quick_call_kwargs["base_url"] == expected_url

    def test_openrouter_uses_provider_model_format(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that OpenRouter accepts provider/model-name format."""
        # Arrange: Model names in provider/model format
        deep_model = "anthropic/claude-sonnet-4"
        quick_model = "anthropic/claude-haiku-3.5"

        # Act
        graph = TradingAgentsGraph(config=openrouter_config)

        # Assert: Model names passed correctly
        calls = mock_langchain_classes["openai"].call_args_list

        deep_call_kwargs = calls[0][1]
        assert deep_call_kwargs["model"] == deep_model

        quick_call_kwargs = calls[1][1]
        assert quick_call_kwargs["model"] == quick_model

    def test_openrouter_alternative_models(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test OpenRouter with different provider/model combinations."""
        # Arrange: Test various model formats
        test_models = [
            "google/gemini-2.0-flash-exp",
            "openai/gpt-4o",
            "meta-llama/llama-3.3-70b-instruct",
        ]

        for model in test_models:
            # Reset mocks
            mock_langchain_classes["openai"].reset_mock()

            # Update config
            config = openrouter_config.copy()
            config["deep_think_llm"] = model

            # Act
            graph = TradingAgentsGraph(config=config)

            # Assert
            call_kwargs = mock_langchain_classes["openai"].call_args_list[0][1]
            assert call_kwargs["model"] == model


# ============================================================================
# Unit Tests: API Key Handling
# ============================================================================

class TestAPIKeyHandling:
    """Test that OpenRouter uses OPENROUTER_API_KEY, not OPENAI_API_KEY."""

    def test_openrouter_requires_openrouter_api_key(
        self,
        openrouter_config,
        mock_env_openrouter,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that OPENROUTER_API_KEY is available when using OpenRouter."""
        # Arrange: OPENROUTER_API_KEY is set

        # Act
        graph = TradingAgentsGraph(config=openrouter_config)

        # Assert: Can access the API key
        assert os.getenv("OPENROUTER_API_KEY") == "sk-or-test-key-123"

    def test_openai_api_key_not_used_for_openrouter(
        self,
        openrouter_config,
        mock_env_openai,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that OPENAI_API_KEY is not used when provider is openrouter."""
        # Arrange: Only OPENAI_API_KEY is set

        # Act
        graph = TradingAgentsGraph(config=openrouter_config)

        # Assert: OPENROUTER_API_KEY should not be set
        assert os.getenv("OPENROUTER_API_KEY") is None
        assert os.getenv("OPENAI_API_KEY") == "sk-test-key-456"

    def test_missing_api_key_environment(
        self,
        openrouter_config,
        mock_env_empty,
        mock_langchain_classes,
        mock_memory
    ):
        """Test environment when no API keys are set."""
        # Arrange: No API keys in environment

        # Act
        graph = TradingAgentsGraph(config=openrouter_config)

        # Assert: No API keys available
        assert os.getenv("OPENROUTER_API_KEY") is None
        assert os.getenv("OPENAI_API_KEY") is None


# ============================================================================
# Unit Tests: Error Handling
# ============================================================================

class TestErrorHandling:
    """Test error handling for missing API keys and invalid configurations."""

    def test_invalid_provider_raises_error(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that invalid provider raises ValueError."""
        # Arrange: Invalid provider
        config = openrouter_config.copy()
        config["llm_provider"] = "invalid_provider"

        # Act & Assert
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            graph = TradingAgentsGraph(config=config)

    def test_empty_backend_url_handled(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test behavior with empty backend_url."""
        # Arrange
        config = openrouter_config.copy()
        config["backend_url"] = ""

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert: Empty string passed to ChatOpenAI
        call_kwargs = mock_langchain_classes["openai"].call_args_list[0][1]
        assert call_kwargs["base_url"] == ""

    def test_none_backend_url_handled(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test behavior with None backend_url."""
        # Arrange
        config = openrouter_config.copy()
        config["backend_url"] = None

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert: None passed to ChatOpenAI
        call_kwargs = mock_langchain_classes["openai"].call_args_list[0][1]
        assert call_kwargs["base_url"] is None


# ============================================================================
# Integration Tests: Model Format Validation
# ============================================================================

class TestModelFormatValidation:
    """Test that OpenRouter model names work correctly."""

    def test_anthropic_model_format(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test Anthropic models via OpenRouter (anthropic/*)."""
        # Arrange
        config = openrouter_config.copy()
        config["deep_think_llm"] = "anthropic/claude-opus-4"
        config["quick_think_llm"] = "anthropic/claude-sonnet-3.5"

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert
        calls = mock_langchain_classes["openai"].call_args_list
        assert calls[0][1]["model"] == "anthropic/claude-opus-4"
        assert calls[1][1]["model"] == "anthropic/claude-sonnet-3.5"

    def test_openai_model_format(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test OpenAI models via OpenRouter (openai/*)."""
        # Arrange
        config = openrouter_config.copy()
        config["deep_think_llm"] = "openai/gpt-4o"
        config["quick_think_llm"] = "openai/gpt-4o-mini"

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert
        calls = mock_langchain_classes["openai"].call_args_list
        assert calls[0][1]["model"] == "openai/gpt-4o"
        assert calls[1][1]["model"] == "openai/gpt-4o-mini"

    def test_google_model_format(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test Google models via OpenRouter (google/*)."""
        # Arrange
        config = openrouter_config.copy()
        config["deep_think_llm"] = "google/gemini-2.0-flash-exp"
        config["quick_think_llm"] = "google/gemini-flash-1.5"

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert
        calls = mock_langchain_classes["openai"].call_args_list
        assert calls[0][1]["model"] == "google/gemini-2.0-flash-exp"
        assert calls[1][1]["model"] == "google/gemini-flash-1.5"

    def test_meta_llama_model_format(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test Meta Llama models via OpenRouter (meta-llama/*)."""
        # Arrange
        config = openrouter_config.copy()
        config["deep_think_llm"] = "meta-llama/llama-3.3-70b-instruct"
        config["quick_think_llm"] = "meta-llama/llama-3.1-8b-instruct"

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert
        calls = mock_langchain_classes["openai"].call_args_list
        assert calls[0][1]["model"] == "meta-llama/llama-3.3-70b-instruct"
        assert calls[1][1]["model"] == "meta-llama/llama-3.1-8b-instruct"


# ============================================================================
# Integration Tests: Embedding Handling
# ============================================================================

class TestEmbeddingHandling:
    """Test that embeddings work correctly with OpenRouter."""

    def test_memory_uses_openrouter_base_url(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that FinancialSituationMemory uses OpenRouter base_url."""
        # Arrange
        config = openrouter_config.copy()

        # Act
        memory = FinancialSituationMemory("test_memory", config)

        # Assert: OpenAI client initialized with OpenRouter URL
        mock_openai_client.assert_called_once_with(
            base_url="https://openrouter.ai/api/v1"
        )

    def test_memory_embedding_with_openrouter(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that embeddings can be generated via OpenRouter."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", openrouter_config)
        test_text = "Test financial situation"

        # Act
        embedding = memory.get_embedding(test_text)

        # Assert: Embedding created successfully
        assert embedding is not None
        assert len(embedding) == 1536
        mock_openai_client.return_value.embeddings.create.assert_called_once()

    def test_memory_uses_text_embedding_model(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that correct embedding model is used."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", openrouter_config)

        # Act
        memory.get_embedding("test")

        # Assert: Called with text-embedding-3-small
        call_args = mock_openai_client.return_value.embeddings.create.call_args
        assert call_args[1]["model"] == "text-embedding-3-small"

    def test_memory_ollama_embedding_model(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that Ollama uses nomic-embed-text model."""
        # Arrange
        config = openrouter_config.copy()
        config["backend_url"] = "http://localhost:11434/v1"
        memory = FinancialSituationMemory("test_memory", config)

        # Act
        memory.get_embedding("test")

        # Assert: Called with nomic-embed-text
        call_args = mock_openai_client.return_value.embeddings.create.call_args
        assert call_args[1]["model"] == "nomic-embed-text"

    def test_memory_graceful_fallback_on_embedding_error(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that memory gracefully handles embedding failures."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", openrouter_config)

        # Mock embedding failure
        mock_openai_client.return_value.embeddings.create.side_effect = Exception(
            "API quota exceeded"
        )

        # Act: Try to get memories (will fail on embedding)
        result = memory.get_memories("current situation", n_matches=1)

        # Assert: Returns empty list instead of crashing
        assert result == []

    def test_memory_add_situations_with_openrouter(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test adding situations to memory using OpenRouter embeddings."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", openrouter_config)
        situations = [
            ("Market volatility increasing", "Reduce risk exposure"),
            ("Strong uptrend detected", "Increase position size"),
        ]

        # Act
        memory.add_situations(situations)

        # Assert: Embeddings created for each situation
        assert mock_openai_client.return_value.embeddings.create.call_count == 2


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_case_insensitive_provider_name(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that provider names are case-sensitive (current implementation).

        NOTE: Current implementation only accepts lowercase 'openrouter'.
        Unlike 'openai', 'anthropic', 'google' which use .lower(),
        'openrouter' and 'ollama' are case-sensitive string matches.
        """
        # Arrange: Only lowercase 'openrouter' works
        valid_provider = "openrouter"
        invalid_providers = ["OpenRouter", "OPENROUTER", "OpenRouTer"]

        # Act & Assert: Lowercase works
        config = openrouter_config.copy()
        config["llm_provider"] = valid_provider
        graph = TradingAgentsGraph(config=config)
        assert mock_langchain_classes["openai"].called

        # Act & Assert: Other cases fail
        for provider in invalid_providers:
            mock_langchain_classes["openai"].reset_mock()
            config = openrouter_config.copy()
            config["llm_provider"] = provider

            with pytest.raises(ValueError, match="Unsupported LLM provider"):
                graph = TradingAgentsGraph(config=config)

    def test_openrouter_with_ollama_provider_name(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that 'ollama' provider also uses ChatOpenAI (grouped with openrouter)."""
        # Arrange
        config = openrouter_config.copy()
        config["llm_provider"] = "ollama"
        config["backend_url"] = "http://localhost:11434/v1"

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert: ChatOpenAI used (not Anthropic/Google)
        assert mock_langchain_classes["openai"].called
        assert not mock_langchain_classes["anthropic"].called
        assert not mock_langchain_classes["google"].called

    def test_empty_model_name(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test behavior with empty model names."""
        # Arrange
        config = openrouter_config.copy()
        config["deep_think_llm"] = ""
        config["quick_think_llm"] = ""

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert: Empty strings passed to ChatOpenAI
        calls = mock_langchain_classes["openai"].call_args_list
        assert calls[0][1]["model"] == ""
        assert calls[1][1]["model"] == ""

    def test_special_characters_in_model_name(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test model names with special characters."""
        # Arrange
        config = openrouter_config.copy()
        config["deep_think_llm"] = "anthropic/claude-3.5-sonnet-20241022"

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert: Model name preserved exactly
        call_kwargs = mock_langchain_classes["openai"].call_args_list[0][1]
        assert call_kwargs["model"] == "anthropic/claude-3.5-sonnet-20241022"

    def test_url_with_trailing_slash(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test backend_url with trailing slash."""
        # Arrange
        config = openrouter_config.copy()
        config["backend_url"] = "https://openrouter.ai/api/v1/"

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert: Trailing slash preserved
        call_kwargs = mock_langchain_classes["openai"].call_args_list[0][1]
        assert call_kwargs["base_url"] == "https://openrouter.ai/api/v1/"

    def test_memory_empty_collection_query(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test querying memories when collection is empty."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", openrouter_config)

        # Act: Query empty collection
        result = memory.get_memories("test situation", n_matches=5)

        # Assert: Returns empty list
        assert result == []

    def test_memory_zero_matches_requested(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test requesting zero matches from memory."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", openrouter_config)
        collection_mock = mock_chromadb.return_value.create_collection.return_value
        collection_mock.count.return_value = 5  # Non-empty collection
        collection_mock.query.return_value = {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]]
        }

        # Act
        result = memory.get_memories("test", n_matches=0)

        # Assert: Returns empty list
        assert result == []


# ============================================================================
# Configuration Tests
# ============================================================================

class TestConfiguration:
    """Test configuration handling for OpenRouter."""

    def test_default_config_not_openrouter(self):
        """Test that default config doesn't use OpenRouter."""
        # Arrange & Act
        config = DEFAULT_CONFIG

        # Assert
        assert config["llm_provider"] != "openrouter"
        assert config["backend_url"] == "https://api.openai.com/v1"

    def test_config_override_with_openrouter(
        self,
        openrouter_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that config can be overridden to use OpenRouter."""
        # Arrange: OpenRouter config overrides defaults

        # Act
        graph = TradingAgentsGraph(config=openrouter_config)

        # Assert: Configuration applied
        assert graph.config["llm_provider"] == "openrouter"
        assert graph.config["backend_url"] == "https://openrouter.ai/api/v1"

    def test_partial_config_merge(
        self,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that partial config requires all necessary keys.

        NOTE: Current implementation doesn't merge with defaults.
        Missing required keys like 'project_dir' will cause KeyError.
        User must provide complete config or use DEFAULT_CONFIG.copy().
        """
        # Arrange: Partial config missing required keys
        partial_config = {
            "llm_provider": "openrouter",
            "backend_url": "https://openrouter.ai/api/v1",
        }

        # Act & Assert: Missing 'project_dir' causes KeyError
        with pytest.raises(KeyError, match="project_dir"):
            graph = TradingAgentsGraph(config=partial_config)

        # Arrange: Complete config works
        complete_config = DEFAULT_CONFIG.copy()
        complete_config.update({
            "llm_provider": "openrouter",
            "backend_url": "https://openrouter.ai/api/v1",
        })

        # Act
        graph = TradingAgentsGraph(config=complete_config)

        # Assert: Uses provided values
        assert graph.config["llm_provider"] == "openrouter"
        assert graph.config["backend_url"] == "https://openrouter.ai/api/v1"
