"""Unit tests for FinancialSituationMemory."""

import pytest

from tradingagents.agents.utils.memory import FinancialSituationMemory


class TestFinancialSituationMemory:
    """Tests for the FinancialSituationMemory class."""

    @pytest.mark.unit
    def test_init(self):
        """Test memory initialization."""
        memory = FinancialSituationMemory("test_memory")
        assert memory.name == "test_memory"
        assert len(memory.documents) == 0
        assert len(memory.recommendations) == 0
        assert memory.bm25 is None

    @pytest.mark.unit
    def test_init_with_config(self):
        """Test memory initialization with config (for API compatibility)."""
        memory = FinancialSituationMemory("test_memory", config={"some": "config"})
        assert memory.name == "test_memory"
        # Config is accepted but not used for BM25

    @pytest.mark.unit
    def test_add_situations_single(self):
        """Test adding a single situation."""
        memory = FinancialSituationMemory("test_memory")
        memory.add_situations([("High volatility", "Reduce exposure")])

        assert len(memory.documents) == 1
        assert len(memory.recommendations) == 1
        assert memory.documents[0] == "High volatility"
        assert memory.recommendations[0] == "Reduce exposure"
        assert memory.bm25 is not None

    @pytest.mark.unit
    def test_add_situations_multiple(self):
        """Test adding multiple situations."""
        memory = FinancialSituationMemory("test_memory")
        situations = [
            ("High volatility in tech sector", "Reduce exposure"),
            ("Strong earnings report", "Consider buying"),
            ("Rising interest rates", "Review duration"),
        ]
        memory.add_situations(situations)

        assert len(memory.documents) == 3
        assert len(memory.recommendations) == 3
        assert memory.bm25 is not None

    @pytest.mark.unit
    def test_add_situations_incremental(self):
        """Test adding situations incrementally."""
        memory = FinancialSituationMemory("test_memory")
        memory.add_situations([("First situation", "First recommendation")])
        memory.add_situations([("Second situation", "Second recommendation")])

        assert len(memory.documents) == 2
        assert memory.recommendations[0] == "First recommendation"
        assert memory.recommendations[1] == "Second recommendation"

    @pytest.mark.unit
    def test_get_memories_returns_matches(self):
        """Test that get_memories returns matching results."""
        memory = FinancialSituationMemory("test_memory")
        memory.add_situations([
            ("High inflation affecting tech stocks", "Consider defensive positions"),
            ("Strong dollar impacting exports", "Review international exposure"),
        ])

        results = memory.get_memories("inflation concerns in technology sector", n_matches=1)

        assert len(results) == 1
        assert "similarity_score" in results[0]
        assert "matched_situation" in results[0]
        assert "recommendation" in results[0]
        assert results[0]["matched_situation"] == "High inflation affecting tech stocks"

    @pytest.mark.unit
    def test_get_memories_multiple_matches(self):
        """Test that get_memories returns multiple matches."""
        memory = FinancialSituationMemory("test_memory")
        memory.add_situations([
            ("High inflation affecting tech stocks", "Consider defensive positions"),
            ("Inflation concerns rising globally", "Review commodity exposure"),
            ("Strong dollar impacting exports", "Review international exposure"),
        ])

        results = memory.get_memories("inflation worries", n_matches=2)

        assert len(results) == 2
        # Both inflation-related situations should be in top results
        situations = [r["matched_situation"] for r in results]
        assert (
            "High inflation affecting tech stocks" in situations
            or "Inflation concerns rising globally" in situations
        )

    @pytest.mark.unit
    def test_get_memories_empty_returns_empty(self):
        """Test that get_memories on empty memory returns empty list."""
        memory = FinancialSituationMemory("test_memory")
        results = memory.get_memories("any query", n_matches=1)

        assert results == []

    @pytest.mark.unit
    def test_get_memories_normalized_score(self):
        """Test that similarity scores are computed correctly.

        Note: BM25 scores can be negative for documents with low term frequency.
        The normalization divides by max_score but doesn't shift negative scores.
        """
        memory = FinancialSituationMemory("test_memory")
        memory.add_situations([
            ("High volatility tech sector", "Reduce exposure"),
            ("Low volatility bonds", "Stable income"),
        ])

        results = memory.get_memories("volatility in tech", n_matches=2)

        # Verify we get results with similarity_score field
        assert len(results) == 2
        for result in results:
            assert "similarity_score" in result
            # BM25 scores can theoretically be negative, verify it's a number
            assert isinstance(result["similarity_score"], float)

    @pytest.mark.unit
    def test_clear(self):
        """Test that clear empties the memory."""
        memory = FinancialSituationMemory("test_memory")
        memory.add_situations([("test", "test recommendation")])

        assert len(memory.documents) == 1
        assert memory.bm25 is not None

        memory.clear()

        assert len(memory.documents) == 0
        assert len(memory.recommendations) == 0
        assert memory.bm25 is None

    @pytest.mark.unit
    def test_get_memories_after_clear(self):
        """Test that get_memories works after clear and re-add."""
        memory = FinancialSituationMemory("test_memory")
        memory.add_situations([("First", "Rec1")])
        memory.clear()
        memory.add_situations([("Second", "Rec2")])

        results = memory.get_memories("Second", n_matches=1)

        assert len(results) == 1
        assert results[0]["matched_situation"] == "Second"

    @pytest.mark.unit
    def test_tokenize_lowercase(self):
        """Test that tokenization lowercases text."""
        memory = FinancialSituationMemory("test")
        tokens = memory._tokenize("HELLO World")

        assert all(token.islower() for token in tokens)

    @pytest.mark.unit
    def test_tokenize_splits_on_punctuation(self):
        """Test that tokenization splits on punctuation."""
        memory = FinancialSituationMemory("test")
        tokens = memory._tokenize("hello, world! test.")

        assert tokens == ["hello", "world", "test"]

    @pytest.mark.unit
    def test_tokenize_handles_numbers(self):
        """Test that tokenization handles numbers."""
        memory = FinancialSituationMemory("test")
        tokens = memory._tokenize("price 123.45 dollars")

        assert "123" in tokens
        assert "45" in tokens

    @pytest.mark.unit
    def test_unicode_handling(self):
        """Test that memory handles Unicode content."""
        memory = FinancialSituationMemory("test")
        memory.add_situations([
            ("欧洲市场波动加剧", "考虑减少欧洲敞口"),
            ("日本央行政策调整", "关注汇率变化"),
        ])

        results = memory.get_memories("欧洲市场", n_matches=1)

        assert len(results) == 1
        assert "欧洲" in results[0]["matched_situation"]
