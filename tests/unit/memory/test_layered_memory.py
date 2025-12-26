"""Tests for Issue #18: Layered Memory System implementing FinMem pattern.

This module tests the layered memory system with three scoring dimensions:
- Recency: Time-based decay
- Relevancy: Semantic similarity
- Importance: Significance weighting
"""

import pytest
import math
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from tradingagents.memory.layered_memory import (
    LayeredMemory,
    MemoryEntry,
    MemoryConfig,
    ScoringWeights,
    DecayFunction,
    ImportanceLevel,
    ScoredMemory,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def default_config():
    """Default memory configuration."""
    return MemoryConfig()


@pytest.fixture
def custom_weights():
    """Custom scoring weights."""
    return ScoringWeights(recency=0.4, relevancy=0.4, importance=0.2)


@pytest.fixture
def memory_with_default_config():
    """LayeredMemory instance with default configuration."""
    return LayeredMemory()


@pytest.fixture
def sample_entry():
    """Sample memory entry."""
    return MemoryEntry.create(
        content="Market crash of 10% in tech sector",
        metadata={"recommendation": "Reduce tech exposure"},
        importance=ImportanceLevel.HIGH.value,
        tags=["market", "tech", "crash"],
    )


@pytest.fixture
def multiple_entries():
    """Multiple memory entries with different timestamps and importance."""
    now = datetime.now()
    return [
        MemoryEntry(
            id="entry-1",
            content="Tech sector volatility increased significantly",
            metadata={"recommendation": "Reduce exposure"},
            timestamp=now - timedelta(days=1),
            importance=ImportanceLevel.HIGH.value,
            tags=["tech", "volatility"],
        ),
        MemoryEntry(
            id="entry-2",
            content="Federal Reserve announced rate hike",
            metadata={"recommendation": "Consider defensive positions"},
            timestamp=now - timedelta(days=7),
            importance=ImportanceLevel.CRITICAL.value,
            tags=["fed", "rates"],
        ),
        MemoryEntry(
            id="entry-3",
            content="Minor retail earnings miss",
            metadata={"recommendation": "Monitor retail sector"},
            timestamp=now - timedelta(days=30),
            importance=ImportanceLevel.LOW.value,
            tags=["retail", "earnings"],
        ),
        MemoryEntry(
            id="entry-4",
            content="Normal trading day with slight gains",
            metadata={"recommendation": "Hold positions"},
            timestamp=now - timedelta(hours=6),
            importance=ImportanceLevel.MINIMAL.value,
            tags=["normal"],
        ),
    ]


# =============================================================================
# ScoringWeights Tests
# =============================================================================

class TestScoringWeights:
    """Tests for the ScoringWeights class."""

    def test_default_weights(self):
        """Default weights should be 0.3, 0.5, 0.2."""
        weights = ScoringWeights()
        assert weights.recency == 0.3
        assert weights.relevancy == 0.5
        assert weights.importance == 0.2

    def test_custom_weights(self):
        """Custom weights should be stored correctly."""
        weights = ScoringWeights(recency=0.4, relevancy=0.4, importance=0.2)
        assert weights.recency == 0.4
        assert weights.relevancy == 0.4
        assert weights.importance == 0.2

    def test_total_property(self):
        """Total should return sum of all weights."""
        weights = ScoringWeights(recency=0.3, relevancy=0.5, importance=0.2)
        assert weights.total == 1.0

    def test_normalized_weights(self):
        """Normalized weights should sum to 1.0."""
        weights = ScoringWeights(recency=2.0, relevancy=4.0, importance=4.0)
        normalized = weights.normalized()
        assert normalized.recency == 0.2
        assert normalized.relevancy == 0.4
        assert normalized.importance == 0.4
        assert abs(normalized.total - 1.0) < 1e-10

    def test_normalized_zero_weights(self):
        """Zero weights should normalize to equal weights."""
        weights = ScoringWeights(recency=0, relevancy=0, importance=0)
        normalized = weights.normalized()
        assert abs(normalized.recency - 1/3) < 1e-10
        assert abs(normalized.relevancy - 1/3) < 1e-10
        assert abs(normalized.importance - 1/3) < 1e-10

    def test_negative_weights_raise_error(self):
        """Negative weights should raise ValueError."""
        with pytest.raises(ValueError):
            ScoringWeights(recency=-0.1, relevancy=0.5, importance=0.2)


# =============================================================================
# MemoryConfig Tests
# =============================================================================

class TestMemoryConfig:
    """Tests for the MemoryConfig class."""

    def test_default_config(self):
        """Default config should have sensible defaults."""
        config = MemoryConfig()
        assert config.weights.recency == 0.3
        assert config.decay_function == DecayFunction.EXPONENTIAL
        assert config.decay_half_life_days == 7
        assert config.max_age_days == 365
        assert config.default_top_k == 5

    def test_custom_config(self):
        """Custom config values should be stored."""
        config = MemoryConfig(
            weights=ScoringWeights(0.4, 0.4, 0.2),
            decay_function=DecayFunction.LINEAR,
            decay_half_life_days=14,
            max_age_days=180,
        )
        assert config.weights.recency == 0.4
        assert config.decay_function == DecayFunction.LINEAR
        assert config.decay_half_life_days == 14
        assert config.max_age_days == 180


# =============================================================================
# ImportanceLevel Tests
# =============================================================================

class TestImportanceLevel:
    """Tests for the ImportanceLevel enum."""

    def test_critical_value(self):
        """CRITICAL should be 1.0."""
        assert ImportanceLevel.CRITICAL.value == 1.0

    def test_high_value(self):
        """HIGH should be 0.8."""
        assert ImportanceLevel.HIGH.value == 0.8

    def test_medium_value(self):
        """MEDIUM should be 0.5."""
        assert ImportanceLevel.MEDIUM.value == 0.5

    def test_low_value(self):
        """LOW should be 0.2."""
        assert ImportanceLevel.LOW.value == 0.2

    def test_minimal_value(self):
        """MINIMAL should be 0.1."""
        assert ImportanceLevel.MINIMAL.value == 0.1

    def test_ordering(self):
        """Importance levels should be ordered correctly."""
        assert ImportanceLevel.CRITICAL.value > ImportanceLevel.HIGH.value
        assert ImportanceLevel.HIGH.value > ImportanceLevel.MEDIUM.value
        assert ImportanceLevel.MEDIUM.value > ImportanceLevel.LOW.value
        assert ImportanceLevel.LOW.value > ImportanceLevel.MINIMAL.value


# =============================================================================
# MemoryEntry Tests
# =============================================================================

class TestMemoryEntry:
    """Tests for the MemoryEntry class."""

    def test_create_entry(self):
        """Create should generate a valid entry."""
        entry = MemoryEntry.create(
            content="Test content",
            metadata={"key": "value"},
            importance=0.7,
            tags=["test"],
        )
        assert entry.content == "Test content"
        assert entry.metadata == {"key": "value"}
        assert entry.importance == 0.7
        assert entry.tags == ["test"]
        assert entry.id is not None
        assert entry.timestamp is not None

    def test_create_default_values(self):
        """Create with defaults should work."""
        entry = MemoryEntry.create(content="Test")
        assert entry.metadata == {}
        assert entry.importance == 0.5
        assert entry.tags == []

    def test_importance_validation(self):
        """Importance outside [0, 1] should raise error."""
        with pytest.raises(ValueError):
            MemoryEntry.create(content="Test", importance=1.5)

        with pytest.raises(ValueError):
            MemoryEntry.create(content="Test", importance=-0.1)

    def test_age_days(self):
        """Age days should calculate correctly."""
        now = datetime.now()
        entry = MemoryEntry.create(content="Test")
        entry.timestamp = now - timedelta(days=5)

        age = entry.age_days(now)
        assert abs(age - 5.0) < 0.01

    def test_age_days_partial(self):
        """Age days should handle partial days."""
        now = datetime.now()
        entry = MemoryEntry.create(content="Test")
        entry.timestamp = now - timedelta(hours=12)

        age = entry.age_days(now)
        assert abs(age - 0.5) < 0.01

    def test_to_dict(self):
        """To dict should serialize correctly."""
        entry = MemoryEntry.create(
            content="Test",
            metadata={"key": "value"},
            importance=0.8,
            tags=["tag1"],
        )
        data = entry.to_dict()

        assert data["content"] == "Test"
        assert data["metadata"] == {"key": "value"}
        assert data["importance"] == 0.8
        assert data["tags"] == ["tag1"]
        assert "id" in data
        assert "timestamp" in data

    def test_from_dict(self):
        """From dict should deserialize correctly."""
        data = {
            "id": "test-id",
            "content": "Test content",
            "metadata": {"key": "value"},
            "timestamp": "2024-01-15T10:30:00",
            "importance": 0.7,
            "tags": ["tag1", "tag2"],
        }
        entry = MemoryEntry.from_dict(data)

        assert entry.id == "test-id"
        assert entry.content == "Test content"
        assert entry.metadata == {"key": "value"}
        assert entry.importance == 0.7
        assert entry.tags == ["tag1", "tag2"]


# =============================================================================
# DecayFunction Tests
# =============================================================================

class TestDecayFunction:
    """Tests for different decay functions."""

    def test_exponential_decay(self):
        """Exponential decay should decrease over time."""
        config = MemoryConfig(
            decay_function=DecayFunction.EXPONENTIAL,
            decay_lambda=0.1,
        )
        memory = LayeredMemory(config=config)

        now = datetime.now()
        entry_recent = MemoryEntry.create(content="Recent")
        entry_recent.timestamp = now - timedelta(days=1)

        entry_old = MemoryEntry.create(content="Old")
        entry_old.timestamp = now - timedelta(days=30)

        score_recent = memory._calculate_recency_score(entry_recent, now)
        score_old = memory._calculate_recency_score(entry_old, now)

        assert score_recent > score_old
        assert score_recent <= 1.0
        assert score_old >= config.decay_floor

    def test_linear_decay(self):
        """Linear decay should decrease linearly."""
        config = MemoryConfig(
            decay_function=DecayFunction.LINEAR,
            max_age_days=100,
            decay_floor=0.0,
        )
        memory = LayeredMemory(config=config)

        now = datetime.now()
        entry = MemoryEntry.create(content="Test")
        entry.timestamp = now - timedelta(days=50)

        score = memory._calculate_recency_score(entry, now)
        # At 50 days of 100 max, linear decay should be ~0.5
        assert abs(score - 0.5) < 0.01

    def test_step_decay(self):
        """Step decay should drop after half-life."""
        config = MemoryConfig(
            decay_function=DecayFunction.STEP,
            decay_half_life_days=7,
            decay_floor=0.2,
        )
        memory = LayeredMemory(config=config)

        now = datetime.now()

        entry_before = MemoryEntry.create(content="Before")
        entry_before.timestamp = now - timedelta(days=5)

        entry_after = MemoryEntry.create(content="After")
        entry_after.timestamp = now - timedelta(days=10)

        score_before = memory._calculate_recency_score(entry_before, now)
        score_after = memory._calculate_recency_score(entry_after, now)

        assert score_before == 1.0
        assert score_after == 0.2

    def test_power_decay(self):
        """Power decay should follow 1/(1+t)^alpha."""
        config = MemoryConfig(
            decay_function=DecayFunction.POWER,
            decay_lambda=0.5,  # alpha
            decay_floor=0.0,
        )
        memory = LayeredMemory(config=config)

        now = datetime.now()
        entry = MemoryEntry.create(content="Test")
        entry.timestamp = now - timedelta(days=3)

        score = memory._calculate_recency_score(entry, now)
        # At 3 days with alpha=0.5: 1/(1+3)^0.5 = 1/2 = 0.5
        expected = 1 / ((1 + 3) ** 0.5)
        assert abs(score - expected) < 0.01

    def test_decay_floor(self):
        """Decay should never go below floor."""
        config = MemoryConfig(
            decay_function=DecayFunction.EXPONENTIAL,
            decay_lambda=1.0,  # Fast decay
            decay_floor=0.1,
        )
        memory = LayeredMemory(config=config)

        now = datetime.now()
        entry = MemoryEntry.create(content="Very old")
        entry.timestamp = now - timedelta(days=100)

        score = memory._calculate_recency_score(entry, now)
        assert score >= 0.1


# =============================================================================
# Relevancy Scoring Tests
# =============================================================================

class TestRelevancyScoring:
    """Tests for relevancy scoring."""

    def test_word_overlap_identical(self):
        """Identical texts should have similarity 1.0."""
        memory = LayeredMemory()
        score = memory._word_overlap_similarity(
            "tech sector crash",
            "tech sector crash",
        )
        assert score == 1.0

    def test_word_overlap_partial(self):
        """Partial overlap should have intermediate similarity."""
        memory = LayeredMemory()
        score = memory._word_overlap_similarity(
            "tech sector crash today",
            "tech sector rally tomorrow",
        )
        # Common: tech, sector (2)
        # Union: tech, sector, crash, today, rally, tomorrow (6)
        assert abs(score - 2/6) < 0.01

    def test_word_overlap_none(self):
        """No overlap should have similarity 0."""
        memory = LayeredMemory()
        score = memory._word_overlap_similarity(
            "apple banana cherry",
            "dog elephant fox",
        )
        assert score == 0.0

    def test_word_overlap_case_insensitive(self):
        """Word overlap should be case insensitive."""
        memory = LayeredMemory()
        score = memory._word_overlap_similarity(
            "TECH SECTOR",
            "tech sector",
        )
        assert score == 1.0

    def test_cosine_similarity_identical(self):
        """Identical vectors should have cosine similarity 1.0."""
        memory = LayeredMemory()
        vec = [1.0, 2.0, 3.0]
        score = memory._cosine_similarity(vec, vec)
        # Normalized to [0, 1]: (1 + 1) / 2 = 1.0
        assert abs(score - 1.0) < 0.01

    def test_cosine_similarity_orthogonal(self):
        """Orthogonal vectors should have cosine similarity 0.5 (normalized)."""
        memory = LayeredMemory()
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        score = memory._cosine_similarity(vec1, vec2)
        # cos(90°) = 0, normalized to [0, 1]: (0 + 1) / 2 = 0.5
        assert abs(score - 0.5) < 0.01

    def test_cosine_similarity_opposite(self):
        """Opposite vectors should have cosine similarity 0 (normalized)."""
        memory = LayeredMemory()
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [-1.0, 0.0, 0.0]
        score = memory._cosine_similarity(vec1, vec2)
        # cos(180°) = -1, normalized to [0, 1]: (-1 + 1) / 2 = 0
        assert abs(score - 0.0) < 0.01


# =============================================================================
# Importance Scoring Tests
# =============================================================================

class TestImportanceScoring:
    """Tests for importance scoring."""

    def test_auto_importance_critical(self):
        """Returns >= 10% should be CRITICAL."""
        config = MemoryConfig(auto_importance=True)
        memory = LayeredMemory(config=config)

        entry = MemoryEntry.create(
            content="Major market move",
            metadata={"returns": 0.15},
        )
        memory.add(entry)

        score = memory._calculate_importance_score(entry)
        assert score == ImportanceLevel.CRITICAL.value

    def test_auto_importance_high(self):
        """Returns >= 5% should be HIGH."""
        config = MemoryConfig(auto_importance=True)
        memory = LayeredMemory(config=config)

        entry = MemoryEntry.create(
            content="Significant move",
            metadata={"returns": 0.07},
        )
        memory.add(entry)

        score = memory._calculate_importance_score(entry)
        assert score == ImportanceLevel.HIGH.value

    def test_auto_importance_medium(self):
        """Returns >= 1% should be MEDIUM."""
        config = MemoryConfig(auto_importance=True)
        memory = LayeredMemory(config=config)

        entry = MemoryEntry.create(
            content="Normal move",
            metadata={"returns": 0.03},
        )
        memory.add(entry)

        score = memory._calculate_importance_score(entry)
        assert score == ImportanceLevel.MEDIUM.value

    def test_auto_importance_low(self):
        """Returns < 1% should be LOW."""
        config = MemoryConfig(auto_importance=True)
        memory = LayeredMemory(config=config)

        entry = MemoryEntry.create(
            content="Minor move",
            metadata={"returns": 0.005},
        )
        memory.add(entry)

        score = memory._calculate_importance_score(entry)
        assert score == ImportanceLevel.LOW.value

    def test_auto_importance_negative(self):
        """Negative returns should use absolute value."""
        config = MemoryConfig(auto_importance=True)
        memory = LayeredMemory(config=config)

        entry = MemoryEntry.create(
            content="Market crash",
            metadata={"returns": -0.12},
        )
        memory.add(entry)

        score = memory._calculate_importance_score(entry)
        assert score == ImportanceLevel.CRITICAL.value

    def test_manual_importance(self):
        """Manual importance should be used when auto is disabled."""
        config = MemoryConfig(auto_importance=False)
        memory = LayeredMemory(config=config)

        entry = MemoryEntry.create(
            content="Test",
            metadata={"returns": 0.15},  # Would be CRITICAL with auto
            importance=0.3,  # Manual LOW
        )
        memory.add(entry)

        score = memory._calculate_importance_score(entry)
        assert score == 0.3


# =============================================================================
# Combined Scoring Tests
# =============================================================================

class TestCombinedScoring:
    """Tests for combined scoring."""

    def test_combined_score_calculation(self):
        """Combined score should use weighted sum."""
        config = MemoryConfig(
            weights=ScoringWeights(recency=0.3, relevancy=0.5, importance=0.2)
        )
        memory = LayeredMemory(config=config)

        # Score = 0.3 * 0.8 + 0.5 * 0.6 + 0.2 * 1.0 = 0.24 + 0.3 + 0.2 = 0.74
        score = memory._calculate_combined_score(
            recency=0.8,
            relevancy=0.6,
            importance=1.0,
        )
        assert abs(score - 0.74) < 0.01

    def test_combined_score_normalized(self):
        """Combined score with non-normalized weights."""
        config = MemoryConfig(
            weights=ScoringWeights(recency=1.0, relevancy=2.0, importance=2.0)
        )
        memory = LayeredMemory(config=config)

        # Normalized: 0.2, 0.4, 0.4
        # Score = 0.2 * 0.5 + 0.4 * 0.5 + 0.4 * 0.5 = 0.1 + 0.2 + 0.2 = 0.5
        score = memory._calculate_combined_score(
            recency=0.5,
            relevancy=0.5,
            importance=0.5,
        )
        assert abs(score - 0.5) < 0.01


# =============================================================================
# LayeredMemory CRUD Tests
# =============================================================================

class TestLayeredMemoryCRUD:
    """Tests for LayeredMemory CRUD operations."""

    def test_add_entry(self, memory_with_default_config, sample_entry):
        """Add should store entry and return ID."""
        memory_id = memory_with_default_config.add(sample_entry)
        assert memory_id == sample_entry.id
        assert memory_with_default_config.count() == 1

    def test_add_batch(self, memory_with_default_config, multiple_entries):
        """Add batch should store all entries."""
        ids = memory_with_default_config.add_batch(multiple_entries)
        assert len(ids) == len(multiple_entries)
        assert memory_with_default_config.count() == len(multiple_entries)

    def test_get_entry(self, memory_with_default_config, sample_entry):
        """Get should return stored entry."""
        memory_with_default_config.add(sample_entry)
        retrieved = memory_with_default_config.get(sample_entry.id)
        assert retrieved is not None
        assert retrieved.content == sample_entry.content

    def test_get_nonexistent(self, memory_with_default_config):
        """Get nonexistent ID should return None."""
        result = memory_with_default_config.get("nonexistent-id")
        assert result is None

    def test_remove_entry(self, memory_with_default_config, sample_entry):
        """Remove should delete entry."""
        memory_with_default_config.add(sample_entry)
        result = memory_with_default_config.remove(sample_entry.id)
        assert result is True
        assert memory_with_default_config.count() == 0

    def test_remove_nonexistent(self, memory_with_default_config):
        """Remove nonexistent ID should return False."""
        result = memory_with_default_config.remove("nonexistent-id")
        assert result is False

    def test_clear(self, memory_with_default_config, multiple_entries):
        """Clear should remove all entries."""
        memory_with_default_config.add_batch(multiple_entries)
        count = memory_with_default_config.clear()
        assert count == len(multiple_entries)
        assert memory_with_default_config.count() == 0

    def test_update_importance(self, memory_with_default_config, sample_entry):
        """Update importance should modify entry."""
        memory_with_default_config.add(sample_entry)
        result = memory_with_default_config.update_importance(sample_entry.id, 0.9)
        assert result is True
        entry = memory_with_default_config.get(sample_entry.id)
        assert entry.importance == 0.9

    def test_update_importance_invalid(self, memory_with_default_config, sample_entry):
        """Update importance with invalid value should raise."""
        memory_with_default_config.add(sample_entry)
        with pytest.raises(ValueError):
            memory_with_default_config.update_importance(sample_entry.id, 1.5)


# =============================================================================
# Retrieval Tests
# =============================================================================

class TestRetrieval:
    """Tests for memory retrieval."""

    def test_retrieve_empty(self, memory_with_default_config):
        """Retrieve from empty memory should return empty list."""
        results = memory_with_default_config.retrieve("test query")
        assert results == []

    def test_retrieve_basic(self, memory_with_default_config, multiple_entries):
        """Basic retrieval should return scored memories."""
        memory_with_default_config.add_batch(multiple_entries)
        results = memory_with_default_config.retrieve(
            query="tech sector volatility",
            top_k=2,
        )
        assert len(results) == 2
        assert all(isinstance(r, ScoredMemory) for r in results)
        # First result should have highest combined score
        assert results[0].combined_score >= results[1].combined_score

    def test_retrieve_respects_top_k(self, memory_with_default_config, multiple_entries):
        """Retrieve should respect top_k limit."""
        memory_with_default_config.add_batch(multiple_entries)
        results = memory_with_default_config.retrieve("query", top_k=2)
        assert len(results) <= 2

    def test_retrieve_by_tags(self, memory_with_default_config, multiple_entries):
        """Retrieve should filter by tags."""
        memory_with_default_config.add_batch(multiple_entries)
        results = memory_with_default_config.retrieve(
            query="market",
            tags=["tech"],
        )
        # Only entries with "tech" tag
        for r in results:
            assert "tech" in r.entry.tags

    def test_retrieve_min_score(self, memory_with_default_config, multiple_entries):
        """Retrieve should filter by min score."""
        memory_with_default_config.add_batch(multiple_entries)
        results = memory_with_default_config.retrieve(
            query="tech",
            min_score=0.5,
        )
        for r in results:
            assert r.combined_score >= 0.5

    def test_retrieve_by_recency(self, memory_with_default_config, multiple_entries):
        """Retrieve by recency should sort by timestamp."""
        memory_with_default_config.add_batch(multiple_entries)
        results = memory_with_default_config.retrieve_by_recency(top_k=3)
        assert len(results) == 3
        # Should be sorted by timestamp descending
        for i in range(len(results) - 1):
            assert results[i].timestamp >= results[i + 1].timestamp

    def test_retrieve_by_importance(self, memory_with_default_config, multiple_entries):
        """Retrieve by importance should sort by importance."""
        memory_with_default_config.add_batch(multiple_entries)
        results = memory_with_default_config.retrieve_by_importance(
            top_k=3,
            min_importance=0.1,
        )
        # Should be sorted by importance descending
        for i in range(len(results) - 1):
            assert results[i].importance >= results[i + 1].importance


# =============================================================================
# Scoring Entry Tests
# =============================================================================

class TestScoreEntry:
    """Tests for score_entry method."""

    def test_score_entry_returns_all_scores(self, memory_with_default_config, sample_entry):
        """Score entry should return all scoring dimensions."""
        memory_with_default_config.add(sample_entry)
        scored = memory_with_default_config.score_entry(
            sample_entry,
            query="tech sector crash",
        )

        assert isinstance(scored, ScoredMemory)
        assert 0 <= scored.recency_score <= 1
        assert 0 <= scored.relevancy_score <= 1
        assert 0 <= scored.importance_score <= 1
        assert 0 <= scored.combined_score <= 1


# =============================================================================
# Statistics Tests
# =============================================================================

class TestStatistics:
    """Tests for get_statistics method."""

    def test_statistics_empty(self, memory_with_default_config):
        """Statistics for empty memory should return zeros."""
        stats = memory_with_default_config.get_statistics()
        assert stats["count"] == 0
        assert stats["oldest"] is None
        assert stats["newest"] is None

    def test_statistics_with_data(self, memory_with_default_config, multiple_entries):
        """Statistics should reflect stored data."""
        memory_with_default_config.add_batch(multiple_entries)
        stats = memory_with_default_config.get_statistics()

        assert stats["count"] == len(multiple_entries)
        assert stats["oldest"] is not None
        assert stats["newest"] is not None
        assert "importance_distribution" in stats


# =============================================================================
# Serialization Tests
# =============================================================================

class TestSerialization:
    """Tests for serialization and deserialization."""

    def test_to_dict(self, memory_with_default_config, multiple_entries):
        """To dict should serialize memory."""
        memory_with_default_config.add_batch(multiple_entries)
        data = memory_with_default_config.to_dict()

        assert "memories" in data
        assert "config" in data
        assert len(data["memories"]) == len(multiple_entries)

    def test_from_dict(self, memory_with_default_config, multiple_entries):
        """From dict should deserialize memory."""
        memory_with_default_config.add_batch(multiple_entries)
        data = memory_with_default_config.to_dict()

        restored = LayeredMemory.from_dict(data)
        assert restored.count() == len(multiple_entries)

    def test_roundtrip(self, memory_with_default_config, sample_entry):
        """Roundtrip serialization should preserve data."""
        memory_with_default_config.add(sample_entry)
        data = memory_with_default_config.to_dict()
        restored = LayeredMemory.from_dict(data)

        original_entry = memory_with_default_config.get(sample_entry.id)
        restored_entry = restored.get(sample_entry.id)

        assert restored_entry is not None
        assert restored_entry.content == original_entry.content
        assert restored_entry.importance == original_entry.importance


# =============================================================================
# Embedding Function Tests
# =============================================================================

class TestEmbeddingFunction:
    """Tests for custom embedding function integration."""

    def test_with_embedding_function(self):
        """Memory with embedding function should use it."""
        def mock_embedding(text: str) -> list:
            # Simple mock: return length-based vector
            return [len(text) / 100, len(text.split()) / 10, 0.5]

        memory = LayeredMemory(embedding_function=mock_embedding)
        entry = MemoryEntry.create(content="Test content for embedding")
        memory.add(entry)

        # Entry should have embedding
        assert entry.embedding is not None
        assert len(entry.embedding) == 3

    def test_embedding_function_failure(self):
        """Failed embedding should not crash."""
        def failing_embedding(text: str) -> list:
            raise RuntimeError("Embedding failed")

        memory = LayeredMemory(embedding_function=failing_embedding)
        entry = MemoryEntry.create(content="Test")

        # Should not raise
        memory_id = memory.add(entry)
        assert memory_id is not None


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_very_old_memory(self):
        """Very old memories should get minimum recency score."""
        config = MemoryConfig(max_age_days=365, decay_floor=0.05)
        memory = LayeredMemory(config=config)

        now = datetime.now()
        entry = MemoryEntry.create(content="Ancient history")
        entry.timestamp = now - timedelta(days=500)
        memory.add(entry)

        score = memory._calculate_recency_score(entry, now)
        assert score == 0.05

    def test_future_timestamp(self):
        """Future timestamps should have maximum recency."""
        memory = LayeredMemory()
        now = datetime.now()
        entry = MemoryEntry.create(content="Future")
        entry.timestamp = now + timedelta(days=1)
        memory.add(entry)

        score = memory._calculate_recency_score(entry, now)
        # Negative age should give high recency
        assert score >= 0.9

    def test_empty_content(self):
        """Empty content should handle gracefully."""
        memory = LayeredMemory()
        score = memory._word_overlap_similarity("", "test")
        assert score == 0.0

    def test_unicode_content(self):
        """Unicode content should work correctly."""
        memory = LayeredMemory()
        entry = MemoryEntry.create(
            content="市场崩盘 📉 Tech crash",
            metadata={"language": "mixed"},
        )
        memory.add(entry)

        results = memory.retrieve(query="Tech crash")
        assert len(results) >= 0  # Should not crash


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the full workflow."""

    def test_full_workflow(self):
        """Test complete memory workflow."""
        # Configure with custom weights
        config = MemoryConfig(
            weights=ScoringWeights(recency=0.3, relevancy=0.5, importance=0.2),
            decay_function=DecayFunction.EXPONENTIAL,
            decay_half_life_days=7,
        )
        memory = LayeredMemory(config=config)

        # Add memories with different characteristics
        now = datetime.now()

        entries = [
            MemoryEntry(
                id="recent-critical",
                content="Tech sector crash of 15%",
                metadata={"recommendation": "Reduce exposure immediately"},
                timestamp=now - timedelta(hours=1),
                importance=ImportanceLevel.CRITICAL.value,
                tags=["tech", "crash"],
            ),
            MemoryEntry(
                id="old-critical",
                content="Previous tech bubble burst",
                metadata={"recommendation": "Historical: went to cash"},
                timestamp=now - timedelta(days=365),
                importance=ImportanceLevel.CRITICAL.value,
                tags=["tech", "historical"],
            ),
            MemoryEntry(
                id="recent-low",
                content="Minor fluctuation in retail",
                metadata={"recommendation": "Hold positions"},
                timestamp=now - timedelta(hours=2),
                importance=ImportanceLevel.LOW.value,
                tags=["retail"],
            ),
        ]

        memory.add_batch(entries)

        # Query for tech-related memories
        results = memory.retrieve(
            query="tech sector volatility crash",
            top_k=3,
        )

        assert len(results) == 3

        # Recent + critical + relevant should be first
        assert results[0].entry.id == "recent-critical"

        # Old but critical and relevant should beat recent but low importance
        # (depends on exact weights and scores)

        # All scores should be valid
        for r in results:
            assert 0 <= r.recency_score <= 1
            assert 0 <= r.relevancy_score <= 1
            assert 0 <= r.importance_score <= 1
            assert 0 <= r.combined_score <= 1

    def test_learning_from_trades(self):
        """Simulate learning from trade outcomes."""
        memory = LayeredMemory()

        # Add past trade memories with outcomes
        trades = [
            {
                "content": "Bought AAPL after earnings beat with bullish guidance",
                "returns": 0.08,
                "recommendation": "Good entry on earnings beat",
            },
            {
                "content": "Shorted TSLA on production delays",
                "returns": -0.05,
                "recommendation": "Avoid shorting high-momentum stocks",
            },
            {
                "content": "Bought SPY on Fed pivot signal",
                "returns": 0.12,
                "recommendation": "Fed pivots are reliable entry points",
            },
        ]

        for trade in trades:
            entry = MemoryEntry.create(
                content=trade["content"],
                metadata={
                    "recommendation": trade["recommendation"],
                    "returns": trade["returns"],
                },
            )
            memory.add(entry)

        # Query for similar situation
        results = memory.retrieve(
            query="considering buying tech stock after earnings",
            top_k=2,
        )

        assert len(results) >= 1
        # Should find relevant trade memories
        for r in results:
            assert r.entry.metadata.get("recommendation") is not None
