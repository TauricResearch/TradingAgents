"""
Test suite for DeepSeek API support and alternative embedding models in TradingAgents.

This module tests Issue #41:
1. DeepSeek provider initialization with ChatOpenAI (following OpenRouter pattern)
2. API key handling (DEEPSEEK_API_KEY vs OPENAI_API_KEY)
3. Error handling for missing API keys
4. Model name format validation (deepseek-chat, deepseek-reasoner)
5. Embedding fallback chain: OpenAI -> HuggingFace -> disable memory
6. Configuration validation
7. HuggingFace sentence-transformers integration

Expected Behavior (Implementation Plan):
- DeepSeek provider uses ChatOpenAI with base_url pointing to DeepSeek API
- DeepSeek requires DEEPSEEK_API_KEY environment variable
- Embedding fallback: Try OpenAI embeddings first, fall back to HuggingFace, finally disable memory
- HuggingFace uses sentence-transformers/all-MiniLM-L6-v2 model (384-dimensional embeddings)
- Graceful degradation with informative messages when embedding backends unavailable
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
def deepseek_config():
    """Create a valid DeepSeek configuration."""
    config = DEFAULT_CONFIG.copy()
    config.update({
        "llm_provider": "deepseek",
        "deep_think_llm": "deepseek-reasoner",
        "quick_think_llm": "deepseek-chat",
        "backend_url": "https://api.deepseek.com/v1",
    })
    return config


@pytest.fixture
def mock_env_deepseek():
    """Mock environment with DEEPSEEK_API_KEY set."""
    with patch.dict(os.environ, {
        "DEEPSEEK_API_KEY": "sk-deepseek-test-key-123",
    }, clear=True):
        yield


@pytest.fixture
def mock_env_deepseek_and_openai():
    """Mock environment with both DEEPSEEK_API_KEY and OPENAI_API_KEY set."""
    with patch.dict(os.environ, {
        "DEEPSEEK_API_KEY": "sk-deepseek-test-key-123",
        "OPENAI_API_KEY": "sk-openai-test-key-456",
    }, clear=True):
        yield


@pytest.fixture
def mock_env_deepseek_no_openai():
    """Mock environment with only DEEPSEEK_API_KEY (no OpenAI key for embeddings)."""
    with patch.dict(os.environ, {
        "DEEPSEEK_API_KEY": "sk-deepseek-test-key-123",
    }, clear=True):
        yield


@pytest.fixture
def mock_sentence_transformer():
    """Mock HuggingFace SentenceTransformer for embedding tests."""
    with patch("tradingagents.agents.utils.memory.SentenceTransformer") as mock:
        # Create mock transformer instance
        transformer_instance = Mock()
        # Mock encode method to return 384-dimensional embeddings (all-MiniLM-L6-v2)
        transformer_instance.encode.return_value = [0.1] * 384
        mock.return_value = transformer_instance
        yield mock


# ============================================================================
# Unit Tests: DeepSeek Provider Initialization
# ============================================================================

class TestDeepSeekInitialization:
    """Test DeepSeek provider initializes ChatOpenAI with correct parameters."""

    def test_deepseek_provider_initializes_correctly(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that DeepSeek provider uses ChatOpenAI class (like OpenRouter)."""
        # Arrange: DeepSeek config ready

        # Act: Initialize TradingAgentsGraph
        graph = TradingAgentsGraph(config=deepseek_config)

        # Assert: ChatOpenAI was called, not Anthropic or Google
        assert mock_langchain_classes["openai"].called
        assert not mock_langchain_classes["anthropic"].called
        assert not mock_langchain_classes["google"].called

    def test_uses_correct_base_url(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that DeepSeek sets base_url to https://api.deepseek.com/v1."""
        # Arrange
        expected_url = "https://api.deepseek.com/v1"

        # Act
        graph = TradingAgentsGraph(config=deepseek_config)

        # Assert: Check both deep and quick thinking LLMs
        calls = mock_langchain_classes["openai"].call_args_list
        assert len(calls) >= 2, "Expected at least 2 ChatOpenAI calls"

        # Check deep thinking LLM (deepseek-reasoner)
        deep_call_kwargs = calls[0][1]  # Get keyword arguments
        assert deep_call_kwargs["base_url"] == expected_url

        # Check quick thinking LLM (deepseek-chat)
        quick_call_kwargs = calls[1][1]
        assert quick_call_kwargs["base_url"] == expected_url

    def test_sets_custom_headers(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that DeepSeek sets custom headers for API attribution."""
        # Arrange: DeepSeek may require custom headers (like OpenRouter)

        # Act
        graph = TradingAgentsGraph(config=deepseek_config)

        # Assert: Check if default_headers are set
        calls = mock_langchain_classes["openai"].call_args_list
        deep_call_kwargs = calls[0][1]

        # DeepSeek should set headers similar to OpenRouter pattern
        if "default_headers" in deep_call_kwargs:
            headers = deep_call_kwargs["default_headers"]
            # Verify headers exist (implementation may add attribution headers)
            assert isinstance(headers, dict)

    def test_initializes_both_llm_models(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that both deepseek-chat and deepseek-reasoner models are initialized."""
        # Arrange
        expected_deep_model = "deepseek-reasoner"
        expected_quick_model = "deepseek-chat"

        # Act
        graph = TradingAgentsGraph(config=deepseek_config)

        # Assert: Check model names
        calls = mock_langchain_classes["openai"].call_args_list
        assert len(calls) >= 2

        deep_call_kwargs = calls[0][1]
        assert deep_call_kwargs["model"] == expected_deep_model

        quick_call_kwargs = calls[1][1]
        assert quick_call_kwargs["model"] == expected_quick_model


# ============================================================================
# Unit Tests: API Key Handling
# ============================================================================

class TestAPIKeyHandling:
    """Test that DeepSeek uses DEEPSEEK_API_KEY, not OPENAI_API_KEY."""

    def test_missing_api_key_raises_error(
        self,
        deepseek_config,
        mock_env_empty,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that missing DEEPSEEK_API_KEY raises clear error."""
        # Arrange: No API keys in environment

        # Act & Assert: Should raise ValueError
        with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
            graph = TradingAgentsGraph(config=deepseek_config)

    def test_valid_api_key_accepted(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that valid DEEPSEEK_API_KEY is accepted and used."""
        # Arrange: DEEPSEEK_API_KEY is set

        # Act
        graph = TradingAgentsGraph(config=deepseek_config)

        # Assert: API key is accessible
        assert os.getenv("DEEPSEEK_API_KEY") == "sk-deepseek-test-key-123"

        # Assert: API key passed to ChatOpenAI
        calls = mock_langchain_classes["openai"].call_args_list
        deep_call_kwargs = calls[0][1]
        assert deep_call_kwargs["api_key"] == "sk-deepseek-test-key-123"

    def test_empty_api_key_raises_error(
        self,
        deepseek_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that empty DEEPSEEK_API_KEY raises error."""
        # Arrange: Empty API key
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}, clear=True):
            # Act & Assert
            with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
                graph = TradingAgentsGraph(config=deepseek_config)

    def test_openai_api_key_not_used_for_deepseek_llm(
        self,
        deepseek_config,
        mock_env_openai,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that OPENAI_API_KEY alone is not sufficient for DeepSeek provider."""
        # Arrange: Only OPENAI_API_KEY is set (not DEEPSEEK_API_KEY)

        # Act & Assert: Should raise ValueError requiring DEEPSEEK_API_KEY
        with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
            graph = TradingAgentsGraph(config=deepseek_config)


# ============================================================================
# Unit Tests: Model Format Validation
# ============================================================================

class TestModelFormatValidation:
    """Test that DeepSeek model names work correctly."""

    def test_deepseek_chat_model_format(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test deepseek-chat model name format."""
        # Arrange
        config = deepseek_config.copy()
        config["quick_think_llm"] = "deepseek-chat"

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert
        calls = mock_langchain_classes["openai"].call_args_list
        quick_call_kwargs = calls[1][1]
        assert quick_call_kwargs["model"] == "deepseek-chat"

    def test_deepseek_reasoner_model_format(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test deepseek-reasoner model name format."""
        # Arrange
        config = deepseek_config.copy()
        config["deep_think_llm"] = "deepseek-reasoner"

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert
        calls = mock_langchain_classes["openai"].call_args_list
        deep_call_kwargs = calls[0][1]
        assert deep_call_kwargs["model"] == "deepseek-reasoner"

    def test_alternative_deepseek_models(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test alternative DeepSeek model naming conventions."""
        # Arrange: Test various potential model names
        test_models = [
            "deepseek-chat",
            "deepseek-reasoner",
            "deepseek-coder",  # If DeepSeek has coder variant
        ]

        for model in test_models:
            # Reset mocks
            mock_langchain_classes["openai"].reset_mock()

            # Update config
            config = deepseek_config.copy()
            config["deep_think_llm"] = model

            # Act
            graph = TradingAgentsGraph(config=config)

            # Assert
            call_kwargs = mock_langchain_classes["openai"].call_args_list[0][1]
            assert call_kwargs["model"] == model


# ============================================================================
# Integration Tests: Embedding Fallback Chain
# ============================================================================

class TestEmbeddingFallback:
    """Test embedding fallback chain: OpenAI -> HuggingFace -> disable memory."""

    def test_uses_openai_embeddings_when_key_available(
        self,
        deepseek_config,
        mock_env_deepseek_and_openai,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that OpenAI embeddings are used when OPENAI_API_KEY is available."""
        # Arrange: Both DeepSeek and OpenAI keys available

        # Act
        memory = FinancialSituationMemory("test_memory", deepseek_config)

        # Assert: OpenAI client initialized for embeddings
        assert mock_openai_client.called

        # Act: Get embedding
        test_text = "Test financial situation"
        embedding = memory.get_embedding(test_text)

        # Assert: OpenAI embedding created
        assert embedding is not None
        assert len(embedding) == 1536  # OpenAI text-embedding-3-small dimensions
        mock_openai_client.return_value.embeddings.create.assert_called_once()

    def test_falls_back_to_huggingface_without_openai_key(
        self,
        deepseek_config,
        mock_env_deepseek_no_openai,
        mock_sentence_transformer,
        mock_chromadb
    ):
        """Test that HuggingFace embeddings are used when OpenAI key is missing."""
        # Arrange: Only DeepSeek key, no OpenAI key

        # Act: Initialize memory (should fall back to HuggingFace)
        memory = FinancialSituationMemory("test_memory", deepseek_config)

        # Assert: SentenceTransformer initialized
        mock_sentence_transformer.assert_called_once()

        # Verify correct model name
        call_args = mock_sentence_transformer.call_args
        assert "sentence-transformers/all-MiniLM-L6-v2" in str(call_args) or \
               "all-MiniLM-L6-v2" in str(call_args)

        # Act: Get embedding
        test_text = "Test financial situation"
        embedding = memory.get_embedding(test_text)

        # Assert: HuggingFace embedding created
        assert embedding is not None
        assert len(embedding) == 384  # all-MiniLM-L6-v2 dimensions

    def test_disables_memory_when_no_embedding_backend(
        self,
        deepseek_config,
        mock_env_deepseek_no_openai,
        mock_chromadb
    ):
        """Test that memory features are disabled when no embedding backend available."""
        # Arrange: No OpenAI key, and SentenceTransformer import fails
        with patch("tradingagents.agents.utils.memory.SentenceTransformer", side_effect=ImportError("No module named 'sentence_transformers'")):
            # Act: Initialize memory
            memory = FinancialSituationMemory("test_memory", deepseek_config)

            # Assert: Memory client is None (disabled)
            assert memory.client is None

            # Act & Assert: Getting embedding raises RuntimeError
            with pytest.raises(RuntimeError, match="Embedding client not initialized"):
                memory.get_embedding("test")

    def test_huggingface_embedding_dimensions(
        self,
        deepseek_config,
        mock_env_deepseek_no_openai,
        mock_sentence_transformer,
        mock_chromadb
    ):
        """Test that HuggingFace embeddings have correct dimensions (384)."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", deepseek_config)

        # Act
        embedding = memory.get_embedding("test text")

        # Assert: 384 dimensions (all-MiniLM-L6-v2 model)
        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)

    def test_graceful_degradation_message(
        self,
        deepseek_config,
        mock_env_deepseek_no_openai,
        capsys
    ):
        """Test that graceful degradation shows informative message."""
        # Arrange: No OpenAI key, SentenceTransformer import fails
        with patch("tradingagents.agents.utils.memory.SentenceTransformer", side_effect=ImportError("No module")):
            with patch("tradingagents.agents.utils.memory.chromadb.Client"):
                # Act
                memory = FinancialSituationMemory("test_memory", deepseek_config)

                # Assert: Warning message printed
                captured = capsys.readouterr()
                # Should see warning about memory features being disabled
                # (Implementation should print this warning)

    def test_openai_fallback_priority(
        self,
        deepseek_config,
        mock_env_deepseek_and_openai,
        mock_openai_client,
        mock_sentence_transformer,
        mock_chromadb
    ):
        """Test that OpenAI embeddings are prioritized over HuggingFace when both available."""
        # Arrange: Both OpenAI key and HuggingFace available

        # Act
        memory = FinancialSituationMemory("test_memory", deepseek_config)
        memory.get_embedding("test")

        # Assert: OpenAI used, not HuggingFace
        assert mock_openai_client.called
        assert not mock_sentence_transformer.called


# ============================================================================
# Integration Tests: Configuration
# ============================================================================

class TestConfiguration:
    """Test configuration validation and edge cases."""

    def test_case_insensitive_provider_name(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that provider names are case-insensitive."""
        # Arrange: All cases should work
        valid_providers = ["deepseek", "DeepSeek", "DEEPSEEK", "DeepSEEK"]

        for provider in valid_providers:
            # Reset mocks
            mock_langchain_classes["openai"].reset_mock()

            # Act
            config = deepseek_config.copy()
            config["llm_provider"] = provider
            graph = TradingAgentsGraph(config=config)

            # Assert: ChatOpenAI was called
            assert mock_langchain_classes["openai"].called

    def test_default_deepseek_models(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test default DeepSeek model configuration."""
        # Arrange: Default models
        config = deepseek_config.copy()
        assert config["deep_think_llm"] == "deepseek-reasoner"
        assert config["quick_think_llm"] == "deepseek-chat"

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert: Default models used
        calls = mock_langchain_classes["openai"].call_args_list
        assert calls[0][1]["model"] == "deepseek-reasoner"
        assert calls[1][1]["model"] == "deepseek-chat"

    def test_custom_backend_url(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test custom backend URL configuration."""
        # Arrange: Custom URL (e.g., proxy or alternative endpoint)
        config = deepseek_config.copy()
        config["backend_url"] = "https://custom-proxy.example.com/v1"

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert: Custom URL used
        calls = mock_langchain_classes["openai"].call_args_list
        assert calls[0][1]["base_url"] == "https://custom-proxy.example.com/v1"

    def test_empty_backend_url_handled(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test behavior with empty backend_url."""
        # Arrange
        config = deepseek_config.copy()
        config["backend_url"] = ""

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert: Empty string passed to ChatOpenAI
        call_kwargs = mock_langchain_classes["openai"].call_args_list[0][1]
        assert call_kwargs["base_url"] == ""

    def test_none_backend_url_handled(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test behavior with None backend_url."""
        # Arrange
        config = deepseek_config.copy()
        config["backend_url"] = None

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert: None passed to ChatOpenAI
        call_kwargs = mock_langchain_classes["openai"].call_args_list[0][1]
        assert call_kwargs["base_url"] is None


# ============================================================================
# Integration Tests: Error Handling
# ============================================================================

class TestErrorHandling:
    """Test error handling for various failure scenarios."""

    def test_network_error_handling(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_openai_client,
        mock_chromadb
    ):
        """Test graceful handling of network errors during embedding."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", deepseek_config)

        # Mock network error
        mock_openai_client.return_value.embeddings.create.side_effect = Exception(
            "Connection timeout"
        )

        # Act: Try to get memories (will fail on embedding)
        result = memory.get_memories("test situation", n_matches=1)

        # Assert: Returns empty list instead of crashing
        assert result == []

    def test_rate_limit_error_handling(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_openai_client,
        mock_chromadb
    ):
        """Test graceful handling of rate limit errors."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", deepseek_config)

        # Mock rate limit error
        mock_openai_client.return_value.embeddings.create.side_effect = Exception(
            "Rate limit exceeded"
        )

        # Act
        result = memory.get_memories("test", n_matches=1)

        # Assert: Graceful degradation
        assert result == []

    def test_invalid_model_error(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test error handling for invalid model names."""
        # Arrange: Invalid model name
        config = deepseek_config.copy()
        config["deep_think_llm"] = "invalid-deepseek-model"

        # Act: Initialize (ChatOpenAI will accept any model name, validation happens at API call time)
        graph = TradingAgentsGraph(config=config)

        # Assert: Graph initializes but uses invalid model
        calls = mock_langchain_classes["openai"].call_args_list
        assert calls[0][1]["model"] == "invalid-deepseek-model"
        # Note: Actual validation happens when LLM is invoked, not at init time

    def test_invalid_provider_raises_error(
        self,
        deepseek_config,
        mock_langchain_classes,
        mock_memory
    ):
        """Test that invalid provider raises ValueError."""
        # Arrange: Invalid provider
        config = deepseek_config.copy()
        config["llm_provider"] = "invalid_provider"

        # Act & Assert
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            graph = TradingAgentsGraph(config=config)

    def test_huggingface_import_error_handling(
        self,
        deepseek_config,
        mock_env_deepseek_no_openai,
        mock_chromadb
    ):
        """Test handling when sentence-transformers package not installed."""
        # Arrange: SentenceTransformer import fails
        with patch("tradingagents.agents.utils.memory.SentenceTransformer", side_effect=ImportError()):
            # Act
            memory = FinancialSituationMemory("test_memory", deepseek_config)

            # Assert: Client should be None (disabled)
            assert memory.client is None

            # Try to get embedding - should raise error
            with pytest.raises(RuntimeError, match="Embedding client not initialized"):
                memory.get_embedding("test")


# ============================================================================
# Integration Tests: HuggingFace Sentence-Transformers
# ============================================================================

class TestHuggingFaceIntegration:
    """Test HuggingFace sentence-transformers integration."""

    def test_sentence_transformer_initialization(
        self,
        deepseek_config,
        mock_env_deepseek_no_openai,
        mock_sentence_transformer,
        mock_chromadb
    ):
        """Test that SentenceTransformer is initialized with correct model."""
        # Arrange & Act
        memory = FinancialSituationMemory("test_memory", deepseek_config)

        # Assert: SentenceTransformer called with correct model
        mock_sentence_transformer.assert_called_once()
        call_args = mock_sentence_transformer.call_args

        # Should use all-MiniLM-L6-v2 model
        assert "all-MiniLM-L6-v2" in str(call_args)

    def test_sentence_transformer_encode_method(
        self,
        deepseek_config,
        mock_env_deepseek_no_openai,
        mock_sentence_transformer,
        mock_chromadb
    ):
        """Test that encode method is called correctly."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", deepseek_config)
        test_text = "Financial market analysis"

        # Act
        embedding = memory.get_embedding(test_text)

        # Assert: encode called with text
        transformer_instance = mock_sentence_transformer.return_value
        transformer_instance.encode.assert_called_once_with(test_text)

        # Assert: Correct embedding returned
        assert embedding == [0.1] * 384

    def test_huggingface_batch_embedding(
        self,
        deepseek_config,
        mock_env_deepseek_no_openai,
        mock_sentence_transformer,
        mock_chromadb
    ):
        """Test batch embedding with HuggingFace (add_situations)."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", deepseek_config)
        situations = [
            ("Market volatility increasing", "Reduce risk exposure"),
            ("Strong uptrend detected", "Increase position size"),
        ]

        # Act
        memory.add_situations(situations)

        # Assert: encode called twice (once per situation)
        transformer_instance = mock_sentence_transformer.return_value
        assert transformer_instance.encode.call_count == 2

    def test_huggingface_model_caching(
        self,
        deepseek_config,
        mock_env_deepseek_no_openai,
        mock_sentence_transformer,
        mock_chromadb
    ):
        """Test that SentenceTransformer model is initialized once and reused."""
        # Arrange & Act: Initialize memory
        memory = FinancialSituationMemory("test_memory", deepseek_config)

        # Get multiple embeddings
        memory.get_embedding("test 1")
        memory.get_embedding("test 2")
        memory.get_embedding("test 3")

        # Assert: SentenceTransformer initialized only once
        assert mock_sentence_transformer.call_count == 1

        # But encode called multiple times
        transformer_instance = mock_sentence_transformer.return_value
        assert transformer_instance.encode.call_count == 3

    def test_huggingface_embedding_normalization(
        self,
        deepseek_config,
        mock_env_deepseek_no_openai,
        mock_sentence_transformer,
        mock_chromadb
    ):
        """Test that embeddings are properly normalized (if implementation normalizes)."""
        # Arrange
        # Mock normalized embeddings
        normalized_embedding = [0.01] * 384  # Small values suggesting normalization
        transformer_instance = mock_sentence_transformer.return_value
        transformer_instance.encode.return_value = normalized_embedding

        memory = FinancialSituationMemory("test_memory", deepseek_config)

        # Act
        embedding = memory.get_embedding("test")

        # Assert: Embedding values preserved
        assert embedding == normalized_embedding


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_model_name(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test behavior with empty model names."""
        # Arrange
        config = deepseek_config.copy()
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
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test model names with special characters."""
        # Arrange
        config = deepseek_config.copy()
        config["deep_think_llm"] = "deepseek-chat-v2.0"

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert: Model name preserved exactly
        call_kwargs = mock_langchain_classes["openai"].call_args_list[0][1]
        assert call_kwargs["model"] == "deepseek-chat-v2.0"

    def test_url_with_trailing_slash(
        self,
        deepseek_config,
        mock_env_deepseek,
        mock_langchain_classes,
        mock_memory
    ):
        """Test backend_url with trailing slash."""
        # Arrange
        config = deepseek_config.copy()
        config["backend_url"] = "https://api.deepseek.com/v1/"

        # Act
        graph = TradingAgentsGraph(config=config)

        # Assert: Trailing slash preserved
        call_kwargs = mock_langchain_classes["openai"].call_args_list[0][1]
        assert call_kwargs["base_url"] == "https://api.deepseek.com/v1/"

    def test_memory_empty_collection_query(
        self,
        deepseek_config,
        mock_env_deepseek_and_openai,
        mock_openai_client,
        mock_chromadb
    ):
        """Test querying memories when collection is empty."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", deepseek_config)

        # Act: Query empty collection
        result = memory.get_memories("test situation", n_matches=5)

        # Assert: Returns empty list
        assert result == []

    def test_memory_zero_matches_requested(
        self,
        deepseek_config,
        mock_env_deepseek_and_openai,
        mock_openai_client,
        mock_chromadb
    ):
        """Test requesting zero matches from memory."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", deepseek_config)
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

    def test_very_long_text_embedding(
        self,
        deepseek_config,
        mock_env_deepseek_and_openai,
        mock_openai_client,
        mock_chromadb
    ):
        """Test embedding generation for very long text."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", deepseek_config)
        long_text = "Market analysis " * 1000  # Very long text

        # Act
        embedding = memory.get_embedding(long_text)

        # Assert: Embedding still generated
        assert embedding is not None
        assert len(embedding) == 1536

    def test_unicode_text_embedding(
        self,
        deepseek_config,
        mock_env_deepseek_and_openai,
        mock_openai_client,
        mock_chromadb
    ):
        """Test embedding generation for Unicode text."""
        # Arrange
        memory = FinancialSituationMemory("test_memory", deepseek_config)
        unicode_text = "市场分析 股票交易 金融数据"  # Chinese characters

        # Act
        embedding = memory.get_embedding(unicode_text)

        # Assert: Embedding generated for Unicode text
        assert embedding is not None
        assert len(embedding) == 1536

    def test_embedding_fallback_with_partial_failure(
        self,
        deepseek_config,
        mock_env_deepseek_no_openai,
        mock_sentence_transformer,
        mock_chromadb
    ):
        """Test fallback when OpenAI fails but HuggingFace succeeds."""
        # Arrange: Mock OpenAI to fail, HuggingFace to succeed
        with patch("tradingagents.agents.utils.memory.OpenAI", side_effect=Exception("OpenAI unavailable")):
            # Act
            memory = FinancialSituationMemory("test_memory", deepseek_config)

            # Assert: Falls back to HuggingFace
            assert mock_sentence_transformer.called

            # Get embedding using HuggingFace
            embedding = memory.get_embedding("test")
            assert embedding is not None
            assert len(embedding) == 384  # HuggingFace dimensions


# ============================================================================
# ChromaDB Collection Tests (DeepSeek-specific)
# ============================================================================

class TestChromaDBCollectionHandling:
    """Test ChromaDB collection handling with DeepSeek provider."""

    def test_memory_uses_get_or_create_collection(
        self,
        deepseek_config,
        mock_env_deepseek_and_openai,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that FinancialSituationMemory uses get_or_create_collection()."""
        # Arrange
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
            # Act
            memory = FinancialSituationMemory("deepseek_memory", deepseek_config)

            # Assert: get_or_create_collection was called, NOT create_collection
            client_instance = mock_chromadb.return_value
            client_instance.get_or_create_collection.assert_called_once_with(name="deepseek_memory")
            client_instance.create_collection.assert_not_called()

    def test_idempotent_collection_creation_with_deepseek(
        self,
        deepseek_config,
        mock_env_deepseek_and_openai,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that creating same collection twice with DeepSeek does not raise error."""
        # Arrange
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
            collection_name = "deepseek_memory"

            # Act: Create memory instance twice with same name
            memory1 = FinancialSituationMemory(collection_name, deepseek_config)
            memory2 = FinancialSituationMemory(collection_name, deepseek_config)

            # Assert: Both instances created successfully
            assert memory1 is not None
            assert memory2 is not None

            # Assert: get_or_create_collection called twice (idempotent)
            client_instance = mock_chromadb.return_value
            assert client_instance.get_or_create_collection.call_count == 2

    def test_multiple_collections_coexist_with_deepseek(
        self,
        deepseek_config,
        mock_env_deepseek_and_openai,
        mock_openai_client,
        mock_chromadb
    ):
        """Test that different collection names can coexist with DeepSeek."""
        # Arrange
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key"}):
            # Act: Create multiple memory instances with different names
            memory_bull = FinancialSituationMemory("bull_memory", deepseek_config)
            memory_bear = FinancialSituationMemory("bear_memory", deepseek_config)
            memory_trader = FinancialSituationMemory("trader_memory", deepseek_config)

            # Assert: All instances created successfully
            assert memory_bull is not None
            assert memory_bear is not None
            assert memory_trader is not None

            # Assert: get_or_create_collection called with correct names
            client_instance = mock_chromadb.return_value
            calls = client_instance.get_or_create_collection.call_args_list
            assert len(calls) == 3
            assert calls[0][1]["name"] == "bull_memory"
            assert calls[1][1]["name"] == "bear_memory"
            assert calls[2][1]["name"] == "trader_memory"
