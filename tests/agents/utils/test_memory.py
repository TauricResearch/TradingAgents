from unittest.mock import Mock, patch

import pytest

from tradingagents.agents.utils.memory import FinancialSituationMemory


class TestFinancialSituationMemory:
    """Test suite for FinancialSituationMemory class."""

    @pytest.fixture
    def mock_config_openai(self):
        """Fixture for OpenAI configuration."""
        return {
            "backend_url": "https://api.openai.com/v1",
            "llm_provider": "openai",
        }

    @pytest.fixture
    def mock_config_ollama(self):
        """Fixture for Ollama configuration."""
        return {
            "backend_url": "http://localhost:11434/v1",
            "llm_provider": "ollama",
        }

    @patch("tradingagents.agents.utils.memory.OpenAI")
    @patch("tradingagents.agents.utils.memory.chromadb.Client")
    def test_init_with_openai_backend(
        self, mock_chroma, mock_openai, mock_config_openai
    ):
        """Test initialization with OpenAI backend."""
        mock_collection = Mock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        memory = FinancialSituationMemory("test_memory", mock_config_openai)

        assert memory.embedding == "text-embedding-3-small"
        mock_openai.assert_called_once_with(base_url="https://api.openai.com/v1")

    @patch("tradingagents.agents.utils.memory.OpenAI")
    @patch("tradingagents.agents.utils.memory.chromadb.Client")
    def test_init_with_ollama_backend(
        self, mock_chroma, mock_openai, mock_config_ollama
    ):
        """Test initialization with Ollama backend."""
        mock_collection = Mock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        memory = FinancialSituationMemory("test_memory", mock_config_ollama)

        assert memory.embedding == "nomic-embed-text"
        mock_openai.assert_called_once_with(base_url="http://localhost:11434/v1")

    @patch("tradingagents.agents.utils.memory.OpenAI")
    @patch("tradingagents.agents.utils.memory.chromadb.Client")
    def test_collection_creation(self, mock_chroma, mock_openai, mock_config_openai):
        """Test that ChromaDB collection is created with correct name."""
        mock_collection = Mock()
        mock_chroma_instance = Mock()
        mock_chroma.return_value = mock_chroma_instance
        mock_chroma_instance.get_or_create_collection.return_value = mock_collection

        memory = FinancialSituationMemory("my_test_collection", mock_config_openai)

        mock_chroma_instance.get_or_create_collection.assert_called_once_with(
            name="my_test_collection"
        )
        assert memory.situation_collection == mock_collection

    @patch("tradingagents.agents.utils.memory.OpenAI")
    @patch("tradingagents.agents.utils.memory.chromadb.Client")
    def test_get_embedding(self, mock_chroma, mock_openai, mock_config_openai):
        """Test get_embedding method returns correct embedding vector."""
        mock_collection = Mock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        mock_client = Mock()
        mock_openai.return_value = mock_client

        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1, 0.2, 0.3, 0.4])]
        mock_client.embeddings.create.return_value = mock_response

        memory = FinancialSituationMemory("test_memory", mock_config_openai)
        embedding = memory.get_embedding("test text")

        assert embedding == [0.1, 0.2, 0.3, 0.4]
        mock_client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small", input="test text"
        )

    @patch("tradingagents.agents.utils.memory.OpenAI")
    @patch("tradingagents.agents.utils.memory.chromadb.Client")
    def test_get_embedding_with_ollama(
        self, mock_chroma, mock_openai, mock_config_ollama
    ):
        """Test get_embedding uses correct model for Ollama."""
        mock_collection = Mock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        mock_client = Mock()
        mock_openai.return_value = mock_client

        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.5, 0.6])]
        mock_client.embeddings.create.return_value = mock_response

        memory = FinancialSituationMemory("test_memory", mock_config_ollama)
        embedding = memory.get_embedding("ollama test")

        mock_client.embeddings.create.assert_called_once_with(
            model="nomic-embed-text", input="ollama test"
        )

    @patch("tradingagents.agents.utils.memory.OpenAI")
    @patch("tradingagents.agents.utils.memory.chromadb.Client")
    def test_add_situations_single(self, mock_chroma, mock_openai, mock_config_openai):
        """Test adding a single situation and advice pair."""
        mock_collection = Mock()
        mock_collection.count.return_value = 0
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        mock_client = Mock()
        mock_openai.return_value = mock_client
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1, 0.2])]
        mock_client.embeddings.create.return_value = mock_response

        memory = FinancialSituationMemory("test_memory", mock_config_openai)

        situations_and_advice = [("High volatility market", "Reduce position sizes")]

        memory.add_situations(situations_and_advice)

        mock_collection.add.assert_called_once()
        call_kwargs = mock_collection.add.call_args[1]

        assert call_kwargs["documents"] == ["High volatility market"]
        assert call_kwargs["metadatas"] == [{"recommendation": "Reduce position sizes"}]
        assert call_kwargs["ids"] == ["0"]
        assert len(call_kwargs["embeddings"]) == 1

    @patch("tradingagents.agents.utils.memory.OpenAI")
    @patch("tradingagents.agents.utils.memory.chromadb.Client")
    def test_add_situations_multiple(
        self, mock_chroma, mock_openai, mock_config_openai
    ):
        """Test adding multiple situations at once."""
        mock_collection = Mock()
        mock_collection.count.return_value = 0
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        mock_client = Mock()
        mock_openai.return_value = mock_client
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1, 0.2])]
        mock_client.embeddings.create.return_value = mock_response

        memory = FinancialSituationMemory("test_memory", mock_config_openai)

        situations_and_advice = [
            ("Bull market conditions", "Increase long positions"),
            ("Bear market conditions", "Increase short positions"),
            ("Sideways market", "Use range trading strategies"),
        ]

        memory.add_situations(situations_and_advice)

        mock_collection.add.assert_called_once()
        call_kwargs = mock_collection.add.call_args[1]

        assert len(call_kwargs["documents"]) == 3
        assert len(call_kwargs["metadatas"]) == 3
        assert call_kwargs["ids"] == ["0", "1", "2"]

    @patch("tradingagents.agents.utils.memory.OpenAI")
    @patch("tradingagents.agents.utils.memory.chromadb.Client")
    def test_add_situations_with_existing_offset(
        self, mock_chroma, mock_openai, mock_config_openai
    ):
        """Test that ID offset is calculated correctly when adding to existing collection."""
        mock_collection = Mock()
        mock_collection.count.return_value = 5  # Already has 5 items
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        mock_client = Mock()
        mock_openai.return_value = mock_client
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1, 0.2])]
        mock_client.embeddings.create.return_value = mock_response

        memory = FinancialSituationMemory("test_memory", mock_config_openai)

        situations_and_advice = [
            ("New situation", "New advice"),
            ("Another situation", "Another advice"),
        ]

        memory.add_situations(situations_and_advice)

        call_kwargs = mock_collection.add.call_args[1]

        # IDs should start from 5 (the existing count)
        assert call_kwargs["ids"] == ["5", "6"]

    @patch("tradingagents.agents.utils.memory.OpenAI")
    @patch("tradingagents.agents.utils.memory.chromadb.Client")
    def test_get_memories_single_match(
        self, mock_chroma, mock_openai, mock_config_openai
    ):
        """Test retrieving a single matching memory."""
        mock_collection = Mock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        mock_client = Mock()
        mock_openai.return_value = mock_client
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1, 0.2])]
        mock_client.embeddings.create.return_value = mock_response

        # Mock query results
        mock_collection.query.return_value = {
            "documents": [["Similar market condition"]],
            "metadatas": [[{"recommendation": "Apply defensive strategy"}]],
            "distances": [[0.15]],
        }

        memory = FinancialSituationMemory("test_memory", mock_config_openai)
        results = memory.get_memories("Current volatile market", n_matches=1)

        assert len(results) == 1
        assert results[0]["matched_situation"] == "Similar market condition"
        assert results[0]["recommendation"] == "Apply defensive strategy"
        assert results[0]["similarity_score"] == pytest.approx(
            0.85, rel=0.01
        )  # 1 - 0.15

    @patch("tradingagents.agents.utils.memory.OpenAI")
    @patch("tradingagents.agents.utils.memory.chromadb.Client")
    def test_get_memories_multiple_matches(
        self, mock_chroma, mock_openai, mock_config_openai
    ):
        """Test retrieving multiple matching memories."""
        mock_collection = Mock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        mock_client = Mock()
        mock_openai.return_value = mock_client
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1, 0.2])]
        mock_client.embeddings.create.return_value = mock_response

        # Mock query results with 3 matches
        mock_collection.query.return_value = {
            "documents": [["Match 1", "Match 2", "Match 3"]],
            "metadatas": [
                [
                    {"recommendation": "Advice 1"},
                    {"recommendation": "Advice 2"},
                    {"recommendation": "Advice 3"},
                ]
            ],
            "distances": [[0.1, 0.2, 0.3]],
        }

        memory = FinancialSituationMemory("test_memory", mock_config_openai)
        results = memory.get_memories("Query situation", n_matches=3)

        assert len(results) == 3
        assert results[0]["matched_situation"] == "Match 1"
        assert results[1]["matched_situation"] == "Match 2"
        assert results[2]["matched_situation"] == "Match 3"
        assert results[0]["similarity_score"] > results[1]["similarity_score"]
        assert results[1]["similarity_score"] > results[2]["similarity_score"]

    @patch("tradingagents.agents.utils.memory.OpenAI")
    @patch("tradingagents.agents.utils.memory.chromadb.Client")
    def test_get_memories_similarity_scores(
        self, mock_chroma, mock_openai, mock_config_openai
    ):
        """Test that similarity scores are calculated correctly (1 - distance)."""
        mock_collection = Mock()
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        mock_client = Mock()
        mock_openai.return_value = mock_client
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1, 0.2])]
        mock_client.embeddings.create.return_value = mock_response

        mock_collection.query.return_value = {
            "documents": [["Situation A", "Situation B"]],
            "metadatas": [[{"recommendation": "A"}, {"recommendation": "B"}]],
            "distances": [[0.0, 0.5]],  # Perfect match and moderate match
        }

        memory = FinancialSituationMemory("test_memory", mock_config_openai)
        results = memory.get_memories("Test query", n_matches=2)

        assert results[0]["similarity_score"] == pytest.approx(1.0, rel=0.01)  # 1 - 0.0
        assert results[1]["similarity_score"] == pytest.approx(0.5, rel=0.01)  # 1 - 0.5

    @patch("tradingagents.agents.utils.memory.OpenAI")
    @patch("tradingagents.agents.utils.memory.chromadb.Client")
    def test_add_situations_empty_list(
        self, mock_chroma, mock_openai, mock_config_openai
    ):
        """Test adding an empty list of situations."""
        mock_collection = Mock()
        mock_collection.count.return_value = 0
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        mock_client = Mock()
        mock_openai.return_value = mock_client

        memory = FinancialSituationMemory("test_memory", mock_config_openai)
        memory.add_situations([])

        # add should still be called, but with empty lists
        mock_collection.add.assert_called_once()
        call_kwargs = mock_collection.add.call_args[1]
        assert call_kwargs["documents"] == []
        assert call_kwargs["metadatas"] == []
        assert call_kwargs["ids"] == []

    @patch("tradingagents.agents.utils.memory.OpenAI")
    @patch("tradingagents.agents.utils.memory.chromadb.Client")
    def test_memory_different_collection_names(
        self, mock_chroma, mock_openai, mock_config_openai
    ):
        """Test that different memory instances have different collection names."""
        mock_chroma_instance = Mock()
        mock_chroma.return_value = mock_chroma_instance
        mock_chroma_instance.get_or_create_collection.return_value = Mock()

        memory1 = FinancialSituationMemory("bull_memory", mock_config_openai)
        memory2 = FinancialSituationMemory("bear_memory", mock_config_openai)
        memory3 = FinancialSituationMemory("trader_memory", mock_config_openai)

        calls = mock_chroma_instance.get_or_create_collection.call_args_list
        assert len(calls) == 3
        assert calls[0][1]["name"] == "bull_memory"
        assert calls[1][1]["name"] == "bear_memory"
        assert calls[2][1]["name"] == "trader_memory"
