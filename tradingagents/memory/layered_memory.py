"""Layered Memory System implementing the FinMem pattern.

The FinMem pattern uses three scoring dimensions for memory retrieval:
1. Recency Score: Time-based decay - more recent memories are weighted higher
2. Relevancy Score: Semantic similarity - how relevant is this memory to the query
3. Importance Score: Significance weighting - important events are weighted higher

Final retrieval score: score = w_recency * recency + w_relevancy * relevancy + w_importance * importance

Issue #18: [MEM-17] Layered memory - recency, relevancy, importance scoring
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
import math
import uuid


class DecayFunction(Enum):
    """Decay function types for recency scoring."""
    EXPONENTIAL = "exponential"  # e^(-lambda * t)
    LINEAR = "linear"            # max(0, 1 - t/T)
    STEP = "step"                # 1 if t < T else decay_floor
    POWER = "power"              # 1 / (1 + t)^alpha


class ImportanceLevel(Enum):
    """Predefined importance levels for common trading events."""
    CRITICAL = 1.0     # Major market events, circuit breakers, >10% moves
    HIGH = 0.8         # Significant gains/losses (>5%), earnings surprises
    MEDIUM = 0.5       # Normal trading, moderate moves (1-5%)
    LOW = 0.2          # Minor events, small moves (<1%)
    MINIMAL = 0.1      # Routine, no significant impact


@dataclass
class ScoringWeights:
    """Weights for combining the three scoring dimensions.

    The weights determine how much each factor contributes to the final score.
    Weights should typically sum to 1.0 but can be adjusted for emphasis.
    """
    recency: float = 0.3
    relevancy: float = 0.5
    importance: float = 0.2

    def __post_init__(self):
        """Validate weights are non-negative."""
        if self.recency < 0 or self.relevancy < 0 or self.importance < 0:
            raise ValueError("All weights must be non-negative")

    @property
    def total(self) -> float:
        """Sum of all weights."""
        return self.recency + self.relevancy + self.importance

    def normalized(self) -> "ScoringWeights":
        """Return normalized weights that sum to 1.0."""
        total = self.total
        if total == 0:
            return ScoringWeights(recency=1/3, relevancy=1/3, importance=1/3)
        return ScoringWeights(
            recency=self.recency / total,
            relevancy=self.relevancy / total,
            importance=self.importance / total,
        )


@dataclass
class MemoryConfig:
    """Configuration for the LayeredMemory system."""

    # Scoring weights
    weights: ScoringWeights = field(default_factory=ScoringWeights)

    # Recency configuration
    decay_function: DecayFunction = DecayFunction.EXPONENTIAL
    decay_lambda: float = 0.1  # For exponential: e^(-lambda * days)
    decay_half_life_days: int = 7  # Alternative: half-life in days
    decay_floor: float = 0.1  # Minimum recency score
    max_age_days: int = 365  # Maximum age to consider

    # Relevancy configuration
    min_relevancy_threshold: float = 0.0  # Minimum similarity to include
    normalize_relevancy: bool = True  # Normalize to [0, 1]

    # Importance configuration
    auto_importance: bool = True  # Automatically calculate importance
    return_threshold_high: float = 0.05  # >5% return = HIGH importance
    return_threshold_critical: float = 0.10  # >10% return = CRITICAL

    # Retrieval configuration
    default_top_k: int = 5
    score_threshold: float = 0.0  # Minimum combined score to return


@dataclass
class MemoryEntry:
    """A single memory entry with all scoring dimensions.

    Attributes:
        id: Unique identifier
        content: The memory content (situation description)
        metadata: Additional metadata (recommendations, context, etc.)
        timestamp: When the memory was created
        importance: Importance score [0, 1]
        embedding: Vector embedding (if pre-computed)
        tags: Optional tags for filtering
    """
    id: str
    content: str
    metadata: Dict[str, Any]
    timestamp: datetime
    importance: float = 0.5  # Default to MEDIUM
    embedding: Optional[List[float]] = None
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate importance is in valid range."""
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError(f"Importance must be between 0 and 1, got {self.importance}")

    @classmethod
    def create(
        cls,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
        timestamp: Optional[datetime] = None,
    ) -> "MemoryEntry":
        """Factory method to create a new memory entry."""
        return cls(
            id=str(uuid.uuid4()),
            content=content,
            metadata=metadata or {},
            timestamp=timestamp or datetime.now(),
            importance=importance,
            tags=tags or [],
        )

    def age_days(self, reference_time: Optional[datetime] = None) -> float:
        """Calculate age in days from reference time (default: now)."""
        ref = reference_time or datetime.now()
        delta = ref - self.timestamp
        return delta.total_seconds() / 86400  # Convert seconds to days

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "importance": self.importance,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            content=data["content"],
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            importance=data.get("importance", 0.5),
            tags=data.get("tags", []),
        )


@dataclass
class ScoredMemory:
    """A memory entry with computed scores."""
    entry: MemoryEntry
    recency_score: float
    relevancy_score: float
    importance_score: float
    combined_score: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entry": self.entry.to_dict(),
            "recency_score": self.recency_score,
            "relevancy_score": self.relevancy_score,
            "importance_score": self.importance_score,
            "combined_score": self.combined_score,
        }


class LayeredMemory:
    """Layered Memory System implementing the FinMem pattern.

    This class provides memory storage and retrieval with three-dimensional
    scoring based on recency, relevancy, and importance.

    Example:
        >>> config = MemoryConfig(weights=ScoringWeights(0.3, 0.5, 0.2))
        >>> memory = LayeredMemory(config=config)
        >>>
        >>> # Add a memory
        >>> entry = MemoryEntry.create(
        ...     content="Market crash of 10% in tech sector",
        ...     metadata={"recommendation": "Reduce exposure to tech stocks"},
        ...     importance=ImportanceLevel.CRITICAL.value,
        ... )
        >>> memory.add(entry)
        >>>
        >>> # Retrieve relevant memories
        >>> results = memory.retrieve(
        ...     query="Tech sector volatility increasing",
        ...     top_k=5,
        ... )
    """

    def __init__(
        self,
        config: Optional[MemoryConfig] = None,
        embedding_function: Optional[Callable[[str], List[float]]] = None,
    ):
        """Initialize the layered memory system.

        Args:
            config: Memory configuration (uses defaults if not provided)
            embedding_function: Function to compute embeddings for text.
                                If not provided, uses simple word overlap.
        """
        self.config = config or MemoryConfig()
        self.embedding_function = embedding_function
        self._memories: Dict[str, MemoryEntry] = {}
        self._embeddings: Dict[str, List[float]] = {}

    def add(self, entry: MemoryEntry) -> str:
        """Add a memory entry.

        Args:
            entry: The memory entry to add

        Returns:
            The ID of the added entry
        """
        self._memories[entry.id] = entry

        # Compute and cache embedding if we have an embedding function
        if self.embedding_function is not None:
            try:
                embedding = self.embedding_function(entry.content)
                self._embeddings[entry.id] = embedding
                entry.embedding = embedding
            except Exception:
                pass  # Silently fail if embedding computation fails

        return entry.id

    def add_batch(self, entries: List[MemoryEntry]) -> List[str]:
        """Add multiple memory entries.

        Args:
            entries: List of memory entries to add

        Returns:
            List of IDs of added entries
        """
        return [self.add(entry) for entry in entries]

    def get(self, memory_id: str) -> Optional[MemoryEntry]:
        """Get a memory entry by ID.

        Args:
            memory_id: The ID of the memory to retrieve

        Returns:
            The memory entry or None if not found
        """
        return self._memories.get(memory_id)

    def remove(self, memory_id: str) -> bool:
        """Remove a memory entry.

        Args:
            memory_id: The ID of the memory to remove

        Returns:
            True if removed, False if not found
        """
        if memory_id in self._memories:
            del self._memories[memory_id]
            self._embeddings.pop(memory_id, None)
            return True
        return False

    def clear(self) -> int:
        """Remove all memories.

        Returns:
            Number of memories removed
        """
        count = len(self._memories)
        self._memories.clear()
        self._embeddings.clear()
        return count

    def count(self) -> int:
        """Return the number of memories."""
        return len(self._memories)

    def _calculate_recency_score(
        self,
        entry: MemoryEntry,
        reference_time: Optional[datetime] = None,
    ) -> float:
        """Calculate recency score based on age and decay function.

        Args:
            entry: The memory entry
            reference_time: Reference time for age calculation (default: now)

        Returns:
            Recency score in [0, 1]
        """
        age_days = entry.age_days(reference_time)

        # Skip if too old
        if age_days > self.config.max_age_days:
            return self.config.decay_floor

        decay_func = self.config.decay_function

        if decay_func == DecayFunction.EXPONENTIAL:
            # Calculate lambda from half-life if not explicitly set
            lambda_val = self.config.decay_lambda
            if self.config.decay_half_life_days > 0:
                lambda_val = math.log(2) / self.config.decay_half_life_days
            score = math.exp(-lambda_val * age_days)

        elif decay_func == DecayFunction.LINEAR:
            # Linear decay over max_age_days
            score = max(0, 1 - (age_days / self.config.max_age_days))

        elif decay_func == DecayFunction.STEP:
            # Step function: full score until half-life, then floor
            if age_days < self.config.decay_half_life_days:
                score = 1.0
            else:
                score = self.config.decay_floor

        elif decay_func == DecayFunction.POWER:
            # Power decay: 1 / (1 + days)^alpha (alpha = decay_lambda)
            alpha = self.config.decay_lambda
            score = 1 / ((1 + age_days) ** alpha)
        else:
            score = 1.0

        # Apply floor
        return max(self.config.decay_floor, score)

    def _calculate_relevancy_score(
        self,
        entry: MemoryEntry,
        query: str,
        query_embedding: Optional[List[float]] = None,
    ) -> float:
        """Calculate relevancy score based on semantic similarity.

        Args:
            entry: The memory entry
            query: The query text
            query_embedding: Pre-computed query embedding (optional)

        Returns:
            Relevancy score in [0, 1]
        """
        # If we have embeddings, use cosine similarity
        entry_embedding = self._embeddings.get(entry.id) or entry.embedding

        if entry_embedding is not None and query_embedding is not None:
            return self._cosine_similarity(query_embedding, entry_embedding)

        # Fallback to simple word overlap (Jaccard similarity)
        return self._word_overlap_similarity(query, entry.content)

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity in [-1, 1], normalized to [0, 1]
        """
        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)

        # Normalize from [-1, 1] to [0, 1]
        return (similarity + 1) / 2

    def _word_overlap_similarity(self, text1: str, text2: str) -> float:
        """Calculate word overlap (Jaccard) similarity.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Jaccard similarity in [0, 1]
        """
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _calculate_importance_score(self, entry: MemoryEntry) -> float:
        """Get the importance score for an entry.

        Args:
            entry: The memory entry

        Returns:
            Importance score in [0, 1]
        """
        # If auto_importance is enabled and metadata has return info, calculate
        if self.config.auto_importance:
            returns = entry.metadata.get("returns") or entry.metadata.get("return")
            if returns is not None:
                abs_return = abs(float(returns))
                if abs_return >= self.config.return_threshold_critical:
                    return ImportanceLevel.CRITICAL.value
                elif abs_return >= self.config.return_threshold_high:
                    return ImportanceLevel.HIGH.value
                elif abs_return >= 0.01:  # 1%
                    return ImportanceLevel.MEDIUM.value
                else:
                    return ImportanceLevel.LOW.value

        # Use the entry's stored importance
        return entry.importance

    def _calculate_combined_score(
        self,
        recency: float,
        relevancy: float,
        importance: float,
    ) -> float:
        """Calculate the combined score using configured weights.

        Args:
            recency: Recency score [0, 1]
            relevancy: Relevancy score [0, 1]
            importance: Importance score [0, 1]

        Returns:
            Combined score [0, 1]
        """
        weights = self.config.weights.normalized()
        return (
            weights.recency * recency +
            weights.relevancy * relevancy +
            weights.importance * importance
        )

    def score_entry(
        self,
        entry: MemoryEntry,
        query: str,
        query_embedding: Optional[List[float]] = None,
        reference_time: Optional[datetime] = None,
    ) -> ScoredMemory:
        """Score a memory entry against a query.

        Args:
            entry: The memory entry to score
            query: The query text
            query_embedding: Pre-computed query embedding (optional)
            reference_time: Reference time for recency (default: now)

        Returns:
            ScoredMemory with all scores computed
        """
        recency = self._calculate_recency_score(entry, reference_time)
        relevancy = self._calculate_relevancy_score(entry, query, query_embedding)
        importance = self._calculate_importance_score(entry)
        combined = self._calculate_combined_score(recency, relevancy, importance)

        return ScoredMemory(
            entry=entry,
            recency_score=recency,
            relevancy_score=relevancy,
            importance_score=importance,
            combined_score=combined,
        )

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
        tags: Optional[List[str]] = None,
        reference_time: Optional[datetime] = None,
    ) -> List[ScoredMemory]:
        """Retrieve relevant memories based on query.

        Args:
            query: The query text
            top_k: Maximum number of results (default: config.default_top_k)
            min_score: Minimum combined score (default: config.score_threshold)
            tags: Filter by tags (memories must have at least one matching tag)
            reference_time: Reference time for recency (default: now)

        Returns:
            List of ScoredMemory, sorted by combined_score descending
        """
        if not self._memories:
            return []

        top_k = top_k or self.config.default_top_k
        min_score = min_score if min_score is not None else self.config.score_threshold

        # Compute query embedding if we have an embedding function
        query_embedding = None
        if self.embedding_function is not None:
            try:
                query_embedding = self.embedding_function(query)
            except Exception:
                pass

        # Score all memories
        scored_memories: List[ScoredMemory] = []
        for entry in self._memories.values():
            # Filter by tags if specified
            if tags:
                if not any(tag in entry.tags for tag in tags):
                    continue

            scored = self.score_entry(entry, query, query_embedding, reference_time)

            # Filter by min score
            if scored.combined_score >= min_score:
                scored_memories.append(scored)

        # Sort by combined score descending
        scored_memories.sort(key=lambda x: x.combined_score, reverse=True)

        # Return top_k
        return scored_memories[:top_k]

    def retrieve_by_recency(
        self,
        top_k: Optional[int] = None,
        reference_time: Optional[datetime] = None,
    ) -> List[MemoryEntry]:
        """Retrieve memories sorted by recency only.

        Args:
            top_k: Maximum number of results
            reference_time: Reference time for recency

        Returns:
            List of MemoryEntry, sorted by timestamp descending
        """
        top_k = top_k or self.config.default_top_k
        ref = reference_time or datetime.now()

        entries = list(self._memories.values())
        entries.sort(key=lambda x: x.timestamp, reverse=True)

        return entries[:top_k]

    def retrieve_by_importance(
        self,
        top_k: Optional[int] = None,
        min_importance: Optional[float] = None,
    ) -> List[MemoryEntry]:
        """Retrieve memories sorted by importance only.

        Args:
            top_k: Maximum number of results
            min_importance: Minimum importance score

        Returns:
            List of MemoryEntry, sorted by importance descending
        """
        top_k = top_k or self.config.default_top_k
        min_importance = min_importance or 0.0

        entries = [
            e for e in self._memories.values()
            if self._calculate_importance_score(e) >= min_importance
        ]
        entries.sort(
            key=lambda x: self._calculate_importance_score(x),
            reverse=True,
        )

        return entries[:top_k]

    def update_importance(self, memory_id: str, importance: float) -> bool:
        """Update the importance score of a memory.

        Args:
            memory_id: The ID of the memory to update
            importance: New importance score [0, 1]

        Returns:
            True if updated, False if not found
        """
        if memory_id not in self._memories:
            return False

        if not 0.0 <= importance <= 1.0:
            raise ValueError(f"Importance must be between 0 and 1, got {importance}")

        self._memories[memory_id].importance = importance
        return True

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the memory store.

        Returns:
            Dictionary with memory statistics
        """
        if not self._memories:
            return {
                "count": 0,
                "oldest": None,
                "newest": None,
                "avg_importance": 0.0,
                "importance_distribution": {},
            }

        entries = list(self._memories.values())
        timestamps = [e.timestamp for e in entries]
        importances = [e.importance for e in entries]

        # Count importance levels
        importance_dist = {
            "critical": sum(1 for i in importances if i >= 0.9),
            "high": sum(1 for i in importances if 0.7 <= i < 0.9),
            "medium": sum(1 for i in importances if 0.4 <= i < 0.7),
            "low": sum(1 for i in importances if 0.1 <= i < 0.4),
            "minimal": sum(1 for i in importances if i < 0.1),
        }

        return {
            "count": len(entries),
            "oldest": min(timestamps).isoformat(),
            "newest": max(timestamps).isoformat(),
            "avg_importance": sum(importances) / len(importances),
            "importance_distribution": importance_dist,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the memory store to a dictionary.

        Returns:
            Dictionary representation of the memory store
        """
        return {
            "memories": [e.to_dict() for e in self._memories.values()],
            "config": {
                "weights": {
                    "recency": self.config.weights.recency,
                    "relevancy": self.config.weights.relevancy,
                    "importance": self.config.weights.importance,
                },
                "decay_function": self.config.decay_function.value,
                "decay_lambda": self.config.decay_lambda,
                "decay_half_life_days": self.config.decay_half_life_days,
                "decay_floor": self.config.decay_floor,
                "max_age_days": self.config.max_age_days,
            },
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        embedding_function: Optional[Callable[[str], List[float]]] = None,
    ) -> "LayeredMemory":
        """Create a LayeredMemory from a dictionary.

        Args:
            data: Dictionary representation
            embedding_function: Optional embedding function

        Returns:
            LayeredMemory instance
        """
        config_data = data.get("config", {})
        weights_data = config_data.get("weights", {})

        config = MemoryConfig(
            weights=ScoringWeights(
                recency=weights_data.get("recency", 0.3),
                relevancy=weights_data.get("relevancy", 0.5),
                importance=weights_data.get("importance", 0.2),
            ),
            decay_function=DecayFunction(config_data.get("decay_function", "exponential")),
            decay_lambda=config_data.get("decay_lambda", 0.1),
            decay_half_life_days=config_data.get("decay_half_life_days", 7),
            decay_floor=config_data.get("decay_floor", 0.1),
            max_age_days=config_data.get("max_age_days", 365),
        )

        memory = cls(config=config, embedding_function=embedding_function)

        for entry_data in data.get("memories", []):
            entry = MemoryEntry.from_dict(entry_data)
            memory.add(entry)

        return memory
