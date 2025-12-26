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

pytestmark = pytest.mark.integration

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
        # Mock both create_collection (old) and get_or_create_collection (new)
        client_instance.create_collection.return_value = collection_instance
        client_instance.get_or_create_collection.return_value = collection_instance
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
        mock_env_openrouter,
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
        mock_env_openrouter,
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
        mock_env_openrouter,
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
        mock_env_openrouter,
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
        """Test that OPENAI_API_KEY alone is not sufficient for openrouter provider."""
        # Arrange: Only OPENAI_API_KEY is set (not OPENROUTER_API_KEY)

        # Act & Assert: Should raise ValueError requiring OPENROUTER_API_KEY
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            graph = TradingAgentsGraph(config=openrouter_config)

    def test_missing_api_key_raises_error(
        self,
        openrouter_config,
        mock_env_empty,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that missing OPENROUTER_API_KEY raises clear error."""
        # Arrange: No API keys in environment

        # Act & Assert: Should raise ValueError
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            graph = TradingAgentsGraph(config=openrouter_config)


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
        mock_env_openrouter,
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
        mock_env_openrouter,
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
        mock_env_openrouter,
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
        mock_env_openrouter,
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
        mock_env_openrouter,
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
        mock_env_openrouter,
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
        mock_env_openrouter,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that FinancialSituationMemory uses fallback OpenAI for embeddings."""
        # Arrange - need OPENAI_API_KEY for embeddings when using OpenRouter
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
            config = openrouter_config.copy()

            # Act
            memory = FinancialSituationMemory("test_memory", config)

            # Assert: OpenAI client initialized (for embeddings fallback)
            assert mock_openai_client.called

    def test_memory_embedding_with_openrouter(
        self,
        openrouter_config,
        mock_env_openrouter,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that embeddings can be generated via OpenAI fallback."""
        # Arrange - need OPENAI_API_KEY for embeddings
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
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
        mock_env_openrouter,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that correct embedding model is used."""
        # Arrange - need OPENAI_API_KEY for embeddings
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
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
        mock_env_openrouter,
        mock_openai_client,
        mock_chromadb
    ):
        """Test adding situations to memory using OpenRouter embeddings."""
        # Arrange - need OPENAI_API_KEY for embeddings
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
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
        mock_env_openrouter,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that provider names are case-insensitive.

        Provider names use .lower() comparison, so 'OpenRouter', 'OPENROUTER', etc. all work.
        """
        # Arrange: All cases should work
        valid_providers = ["openrouter", "OpenRouter", "OPENROUTER", "OpenRouTer"]

        for provider in valid_providers:
            # Reset mocks
            mock_langchain_classes["openai"].reset_mock()

            # Act
            config = openrouter_config.copy()
            config["llm_provider"] = provider
            graph = TradingAgentsGraph(config=config)

            # Assert: ChatOpenAI was called
            assert mock_langchain_classes["openai"].called

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
        mock_env_openrouter,
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
        mock_env_openrouter,
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
        mock_env_openrouter,
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
        collection_mock = mock_chromadb.return_value.get_or_create_collection.return_value
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
# ChromaDB Collection Tests
# ============================================================================

class TestChromaDBCollectionHandling:
    """Test ChromaDB collection creation and idempotent behavior.

    This test suite addresses Issue #30: Fix ChromaDB collection [bull_memory]
    already exists error by ensuring get_or_create_collection() is used instead
    of create_collection().
    """

    def test_memory_uses_get_or_create_collection(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that FinancialSituationMemory uses get_or_create_collection().

        This is the primary fix for Issue #30. The method must use
        get_or_create_collection() to avoid errors when collection already exists.
        """
        # Arrange
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
            # Act
            memory = FinancialSituationMemory("bull_memory", openrouter_config)

            # Assert: get_or_create_collection was called, NOT create_collection
            client_instance = mock_chromadb.return_value
            client_instance.get_or_create_collection.assert_called_once_with(name="bull_memory")
            # Verify create_collection was NOT called (old behavior)
            client_instance.create_collection.assert_not_called()

    def test_idempotent_collection_creation(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that creating same collection twice does not raise error.

        Key test for Issue #30: Should be able to instantiate
        FinancialSituationMemory with same name multiple times without error.
        """
        # Arrange
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
            collection_name = "bull_memory"

            # Act: Create memory instance twice with same name
            memory1 = FinancialSituationMemory(collection_name, openrouter_config)
            memory2 = FinancialSituationMemory(collection_name, openrouter_config)

            # Assert: Both instances created successfully
            assert memory1 is not None
            assert memory2 is not None

            # Assert: get_or_create_collection called twice (idempotent)
            client_instance = mock_chromadb.return_value
            assert client_instance.get_or_create_collection.call_count == 2
            calls = client_instance.get_or_create_collection.call_args_list
            assert calls[0][1]["name"] == collection_name
            assert calls[1][1]["name"] == collection_name

    def test_existing_data_preserved_on_reinitialization(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that existing collection data is preserved on re-initialization.

        When get_or_create_collection() is used, existing data should not be lost.
        """
        # Arrange
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
            collection_name = "bull_memory"

            # Mock collection with existing data
            collection_mock = Mock()
            collection_mock.count.return_value = 5  # Simulate 5 existing entries
            collection_mock.query.return_value = {
                "documents": [["Existing situation"]],
                "metadatas": [[{"recommendation": "Existing advice"}]],
                "distances": [[0.1]]
            }

            client_instance = mock_chromadb.return_value
            client_instance.get_or_create_collection.return_value = collection_mock

            # Act: Create first instance, add data, create second instance
            memory1 = FinancialSituationMemory(collection_name, openrouter_config)

            # Simulate that collection now has data
            collection_mock.count.return_value = 5

            memory2 = FinancialSituationMemory(collection_name, openrouter_config)

            # Assert: Second instance sees existing data (count > 0)
            assert memory2.situation_collection.count() == 5

    def test_multiple_collections_coexist(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that different collection names can coexist.

        Should be able to create memory instances with different names.
        """
        # Arrange
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
            # Act: Create multiple memory instances with different names
            memory_bull = FinancialSituationMemory("bull_memory", openrouter_config)
            memory_bear = FinancialSituationMemory("bear_memory", openrouter_config)
            memory_neutral = FinancialSituationMemory("neutral_memory", openrouter_config)

            # Assert: All instances created successfully
            assert memory_bull is not None
            assert memory_bear is not None
            assert memory_neutral is not None

            # Assert: get_or_create_collection called with correct names
            client_instance = mock_chromadb.return_value
            calls = client_instance.get_or_create_collection.call_args_list
            assert len(calls) == 3
            assert calls[0][1]["name"] == "bull_memory"
            assert calls[1][1]["name"] == "bear_memory"
            assert calls[2][1]["name"] == "neutral_memory"

    def test_collection_creation_without_openrouter(
        self,
        mock_openai_client,
        mock_chromadb
    ):
        """Test collection creation works with non-OpenRouter providers."""
        # Arrange
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "openai"
        config["backend_url"] = "https://api.openai.com/v1"

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
            # Act
            memory = FinancialSituationMemory("test_memory", config)

            # Assert: get_or_create_collection still used
            client_instance = mock_chromadb.return_value
            client_instance.get_or_create_collection.assert_called_once_with(name="test_memory")

    def test_collection_name_with_special_characters(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test collection names with special characters."""
        # Arrange
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
            special_names = [
                "bull_memory_v2",
                "memory-2024",
                "memory.test",
                "UPPERCASE_MEMORY",
            ]

            # Act & Assert: All names should work
            for name in special_names:
                memory = FinancialSituationMemory(name, openrouter_config)
                assert memory is not None

    def test_empty_collection_name_handled(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test behavior with empty collection name."""
        # Arrange
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
            # Act: ChromaDB should handle empty name (may raise ValueError)
            # We're testing that our code passes it through correctly
            memory = FinancialSituationMemory("", openrouter_config)

            # Assert: get_or_create_collection called with empty string
            client_instance = mock_chromadb.return_value
            client_instance.get_or_create_collection.assert_called_once_with(name="")

    def test_collection_creation_with_ollama(
        self,
        mock_chromadb
    ):
        """Test collection creation works with Ollama provider."""
        # Arrange
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "ollama"
        config["backend_url"] = "http://localhost:11434/v1"

        with patch("tradingagents.agents.utils.memory.OpenAI") as mock_openai:
            # Mock Ollama client
            client_instance = Mock()
            mock_openai.return_value = client_instance

            # Act
            memory = FinancialSituationMemory("ollama_memory", config)

            # Assert: get_or_create_collection used
            chroma_client = mock_chromadb.return_value
            chroma_client.get_or_create_collection.assert_called_once_with(name="ollama_memory")

    def test_add_situations_to_reinitialized_collection(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test adding situations after re-initializing collection.

        Ensures that offset calculation works correctly when collection
        already has data from previous initialization.
        """
        # Arrange
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
            collection_name = "bull_memory"

            # Mock collection that starts with 3 items
            collection_mock = Mock()
            collection_mock.count.return_value = 3
            collection_mock.add = Mock()  # Track add calls

            client_instance = mock_chromadb.return_value
            client_instance.get_or_create_collection.return_value = collection_mock

            # Act: Create memory instance and add situations
            memory = FinancialSituationMemory(collection_name, openrouter_config)
            new_situations = [
                ("Market trend positive", "Increase position"),
                ("Volatility rising", "Reduce exposure"),
            ]
            memory.add_situations(new_situations)

            # Assert: IDs start at offset 3 (existing count)
            collection_mock.add.assert_called_once()
            call_args = collection_mock.add.call_args[1]
            assert call_args["ids"] == ["3", "4"]  # Offset by existing count

    def test_get_memories_from_reinitialized_collection(
        self,
        openrouter_config,
        mock_openai_client,
        mock_chromadb
    ):
        """Test querying memories from re-initialized collection.

        Verifies that existing data can be queried after re-initialization.
        """
        # Arrange
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
            collection_name = "bull_memory"

            # Mock collection with existing data
            collection_mock = Mock()
            collection_mock.count.return_value = 5
            collection_mock.query.return_value = {
                "documents": [["Previous market analysis"]],
                "metadatas": [[{"recommendation": "Hold positions"}]],
                "distances": [[0.15]]
            }

            client_instance = mock_chromadb.return_value
            client_instance.get_or_create_collection.return_value = collection_mock

            # Mock embedding
            mock_openai_client.return_value.embeddings.create.return_value.data = [
                Mock(embedding=[0.1] * 1536)
            ]

            # Act: Create new instance and query
            memory = FinancialSituationMemory(collection_name, openrouter_config)
            results = memory.get_memories("Current market situation", n_matches=1)

            # Assert: Existing data retrieved
            assert len(results) == 1
            assert results[0]["matched_situation"] == "Previous market analysis"
            assert results[0]["recommendation"] == "Hold positions"


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
        mock_env_openrouter,
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
        mock_env_openrouter,
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
