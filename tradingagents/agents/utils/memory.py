import chromadb
from chromadb.config import Settings
from openai import OpenAI
from typing import List, Dict, Any, Optional, Tuple
import time

from tradingagents.utils.logging_config import (
    get_logger,
    get_api_logger,
    get_performance_logger,
)

logger = get_logger("tradingagents.memory", component="MEMORY")
api_logger = get_api_logger()
perf_logger = get_performance_logger()


class FinancialSituationMemory:
    """
    Memory system for financial trading agents with support for multiple embedding providers.

    Supports:
    - OpenAI embeddings
    - Ollama local embeddings
    - Graceful fallback when embeddings are unavailable
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize the financial situation memory.

        Args:
            name: Name of the memory collection
            config: Configuration dictionary containing embedding settings
        """
        self.name = name
        self.config = config
        self.enabled = config.get("enable_memory", True)

        # Initialize embedding client and model based on provider
        self.embedding_provider = config.get("embedding_provider", "openai").lower()
        self.embedding_model = self._get_embedding_model()
        self.embedding_backend_url = config.get(
            "embedding_backend_url", "https://api.openai.com/v1"
        )

        # Initialize OpenAI client for embeddings (if enabled and supported)
        self.client = None
        if self.enabled and self.embedding_provider in ["openai", "ollama"]:
            try:
                start_time = time.time()
                self.client = OpenAI(base_url=self.embedding_backend_url)
                init_duration = (time.time() - start_time) * 1000

                logger.info(
                    f"Initialized embedding client for '{name}'",
                    extra={
                        "context": {
                            "provider": self.embedding_provider,
                            "backend_url": self.embedding_backend_url,
                            "model": self.embedding_model,
                            "init_time_ms": init_duration,
                        }
                    },
                )
                perf_logger.log_timing(
                    "embedding_client_init",
                    init_duration,
                    {"provider": self.embedding_provider},
                )
            except Exception as e:
                logger.warning(
                    f"Failed to initialize embedding client for '{name}': {e}. Memory will be disabled.",
                    extra={
                        "context": {
                            "provider": self.embedding_provider,
                            "error": str(e),
                        }
                    },
                )
                self.enabled = False
        elif not self.enabled:
            logger.info(f"Memory disabled for '{name}' (enable_memory=False)")
        elif self.embedding_provider == "none":
            logger.info(
                f"Embedding provider set to 'none' for '{name}'. Memory will be disabled."
            )
            self.enabled = False
        else:
            logger.warning(
                f"Unsupported embedding provider '{self.embedding_provider}' for '{name}'. Memory will be disabled."
            )
            self.enabled = False

        # Initialize ChromaDB collection
        self.chroma_client = None
        self.situation_collection = None
        if self.enabled:
            try:
                start_time = time.time()
                self.chroma_client = chromadb.Client(Settings(allow_reset=True))
                self.situation_collection = self.chroma_client.create_collection(
                    name=name
                )
                init_duration = (time.time() - start_time) * 1000

                logger.info(
                    f"Initialized ChromaDB collection '{name}'",
                    extra={
                        "context": {"collection": name, "init_time_ms": init_duration}
                    },
                )
                perf_logger.log_timing(
                    "chromadb_collection_init", init_duration, {"collection": name}
                )
            except Exception as e:
                logger.error(
                    f"Failed to initialize ChromaDB collection '{name}': {e}. Memory will be disabled.",
                    extra={"context": {"collection": name, "error": str(e)}},
                )
                self.enabled = False

    def _get_embedding_model(self) -> str:
        """
        Get the appropriate embedding model based on the provider.

        Returns:
            str: The embedding model name
        """
        # Check if explicitly configured
        if "embedding_model" in self.config:
            return self.config["embedding_model"]

        # Fall back to provider-specific defaults
        if self.embedding_provider == "ollama":
            return "nomic-embed-text"
        elif self.embedding_provider == "openai":
            return "text-embedding-3-small"
        else:
            return "text-embedding-3-small"  # Safe default

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Get embedding for a text using the configured provider.

        Args:
            text: The text to embed

        Returns:
            List of floats representing the embedding, or None if embedding fails
        """
        if not self.enabled or not self.client:
            logger.debug("Embedding skipped (memory disabled or no client)")
            return None

        try:
            start_time = time.time()
            response = self.client.embeddings.create(
                model=self.embedding_model, input=text
            )
            duration = (time.time() - start_time) * 1000

            embedding = response.data[0].embedding

            # Log API call
            api_logger.log_call(
                provider=self.embedding_provider,
                model=self.embedding_model,
                endpoint="embeddings.create",
                tokens=len(text.split()),  # Rough estimate
                duration=duration,
                status="success",
            )

            logger.debug(
                f"Generated embedding for text ({len(text)} chars)",
                extra={
                    "context": {
                        "provider": self.embedding_provider,
                        "model": self.embedding_model,
                        "text_length": len(text),
                        "duration_ms": duration,
                    }
                },
            )

            return embedding
        except Exception as e:
            logger.error(
                f"Failed to get embedding: {e}",
                extra={
                    "context": {
                        "provider": self.embedding_provider,
                        "model": self.embedding_model,
                        "text_length": len(text),
                        "error": str(e),
                    }
                },
            )

            # Log failed API call
            api_logger.log_call(
                provider=self.embedding_provider,
                model=self.embedding_model,
                endpoint="embeddings.create",
                status="error",
                error=str(e),
            )

            return None

    def add_situations(self, situations_and_advice: List[Tuple[str, str]]) -> bool:
        """
        Add financial situations and their corresponding advice.

        Args:
            situations_and_advice: List of tuples (situation, recommendation)

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.enabled:
            logger.debug(
                f"Memory disabled for '{self.name}', skipping add_situations",
                extra={
                    "context": {
                        "collection": self.name,
                        "count": len(situations_and_advice),
                    }
                },
            )
            return False

        try:
            start_time = time.time()
            situations = []
            advice = []
            ids = []
            embeddings = []

            offset = self.situation_collection.count()

            for i, (situation, recommendation) in enumerate(situations_and_advice):
                embedding = self.get_embedding(situation)
                if embedding is None:
                    logger.warning(
                        f"Failed to get embedding for situation {i} in '{self.name}', skipping",
                        extra={
                            "context": {
                                "collection": self.name,
                                "situation_index": i,
                                "situation_preview": situation[:100],
                            }
                        },
                    )
                    continue

                situations.append(situation)
                advice.append(recommendation)
                ids.append(str(offset + i))
                embeddings.append(embedding)

            if not situations:
                logger.warning(
                    f"No valid situations to add to '{self.name}'",
                    extra={
                        "context": {
                            "collection": self.name,
                            "attempted": len(situations_and_advice),
                        }
                    },
                )
                return False

            self.situation_collection.add(
                documents=situations,
                metadatas=[{"recommendation": rec} for rec in advice],
                embeddings=embeddings,
                ids=ids,
            )

            duration = (time.time() - start_time) * 1000

            logger.info(
                f"Added {len(situations)} situations to '{self.name}'",
                extra={
                    "context": {
                        "collection": self.name,
                        "count": len(situations),
                        "total_in_collection": self.situation_collection.count(),
                        "duration_ms": duration,
                    }
                },
            )

            perf_logger.log_timing(
                "add_situations",
                duration,
                {"collection": self.name, "count": len(situations)},
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to add situations to '{self.name}': {e}",
                extra={
                    "context": {
                        "collection": self.name,
                        "attempted_count": len(situations_and_advice),
                        "error": str(e),
                    }
                },
            )
            return False

    def get_memories(
        self, current_situation: str, n_matches: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Find matching recommendations using embeddings.

        Args:
            current_situation: The current situation to match against
            n_matches: Number of matches to return

        Returns:
            List of dictionaries containing matched situations and recommendations.
            Returns empty list if memory is disabled or query fails.
        """
        if not self.enabled:
            logger.debug(
                f"Memory disabled for '{self.name}', returning empty memories",
                extra={"context": {"collection": self.name}},
            )
            return []

        try:
            start_time = time.time()

            query_embedding = self.get_embedding(current_situation)
            if query_embedding is None:
                logger.warning(
                    f"Failed to get query embedding for '{self.name}', returning empty memories",
                    extra={
                        "context": {
                            "collection": self.name,
                            "situation_preview": current_situation[:100],
                        }
                    },
                )
                return []

            results = self.situation_collection.query(
                query_embeddings=[query_embedding],
                n_results=n_matches,
                include=["metadatas", "documents", "distances"],
            )

            matched_results = []
            for i in range(len(results["documents"][0])):
                similarity = 1 - results["distances"][0][i]
                matched_results.append(
                    {
                        "matched_situation": results["documents"][0][i],
                        "recommendation": results["metadatas"][0][i]["recommendation"],
                        "similarity_score": similarity,
                    }
                )

            duration = (time.time() - start_time) * 1000

            logger.info(
                f"Retrieved {len(matched_results)} memories from '{self.name}'",
                extra={
                    "context": {
                        "collection": self.name,
                        "requested": n_matches,
                        "returned": len(matched_results),
                        "top_similarity": matched_results[0]["similarity_score"]
                        if matched_results
                        else 0,
                        "duration_ms": duration,
                    }
                },
            )

            perf_logger.log_timing(
                "get_memories",
                duration,
                {"collection": self.name, "n_matches": n_matches},
            )

            return matched_results

        except Exception as e:
            logger.error(
                f"Failed to get memories from '{self.name}': {e}",
                extra={
                    "context": {
                        "collection": self.name,
                        "n_matches": n_matches,
                        "error": str(e),
                    }
                },
            )
            return []

    def is_enabled(self) -> bool:
        """Check if memory is enabled and functioning."""
        return self.enabled


if __name__ == "__main__":
    # Example usage with OpenAI
    print("=== Testing with OpenAI provider ===")
    config_openai = {
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "embedding_backend_url": "https://api.openai.com/v1",
        "enable_memory": True,
    }

    matcher = FinancialSituationMemory("test_memory", config_openai)

    if matcher.is_enabled():
        # Example data
        example_data = [
            (
                "High inflation rate with rising interest rates and declining consumer spending",
                "Consider defensive sectors like consumer staples and utilities. Review fixed-income portfolio duration.",
            ),
            (
                "Tech sector showing high volatility with increasing institutional selling pressure",
                "Reduce exposure to high-growth tech stocks. Look for value opportunities in established tech companies with strong cash flows.",
            ),
            (
                "Strong dollar affecting emerging markets with increasing forex volatility",
                "Hedge currency exposure in international positions. Consider reducing allocation to emerging market debt.",
            ),
            (
                "Market showing signs of sector rotation with rising yields",
                "Rebalance portfolio to maintain target allocations. Consider increasing exposure to sectors benefiting from higher rates.",
            ),
        ]

        # Add the example situations and recommendations
        if matcher.add_situations(example_data):
            # Example query
            current_situation = """
            Market showing increased volatility in tech sector, with institutional investors
            reducing positions and rising interest rates affecting growth stock valuations
            """

            recommendations = matcher.get_memories(current_situation, n_matches=2)

            for i, rec in enumerate(recommendations, 1):
                print(f"\nMatch {i}:")
                print(f"Similarity Score: {rec['similarity_score']:.2f}")
                print(f"Matched Situation: {rec['matched_situation']}")
                print(f"Recommendation: {rec['recommendation']}")
        else:
            print("Failed to add situations")
    else:
        print("Memory is disabled")

    print("\n=== Testing with disabled memory ===")
    config_disabled = {"embedding_provider": "none", "enable_memory": False}

    matcher_disabled = FinancialSituationMemory("test_disabled", config_disabled)
    print(f"Memory enabled: {matcher_disabled.is_enabled()}")
    result = matcher_disabled.get_memories("test situation")
    print(f"Get memories result: {result}")
