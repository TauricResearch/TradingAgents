import chromadb
from chromadb.config import Settings
from openai import OpenAI
import os

# Try to import HuggingFace sentence-transformers (optional dependency)
# This needs to be at module level for test mocking to work
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None


class FinancialSituationMemory:
    def __init__(self, name, config):
        self.embedding_backend = None  # Track which backend is used

        # Handle embeddings based on provider with fallback chain
        if config["backend_url"] == "http://localhost:11434/v1":
            # Ollama local embeddings
            self.embedding = "nomic-embed-text"
            self.client = OpenAI(base_url=config["backend_url"])
            self.embedding_backend = "ollama"
        elif config.get("llm_provider", "").lower() in ("openrouter", "deepseek"):
            # OpenRouter and DeepSeek don't have native embeddings
            # Fallback chain: OpenAI -> HuggingFace -> disable memory
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                # Use OpenAI embeddings as first fallback
                self.embedding = "text-embedding-3-small"
                self.client = OpenAI(api_key=openai_key)
                self.embedding_backend = "openai"
            elif SentenceTransformer is not None:
                # Use HuggingFace sentence-transformers as second fallback
                try:
                    self.client = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
                    self.embedding = "all-MiniLM-L6-v2"
                    self.embedding_backend = "huggingface"
                    print(f"Info: Using HuggingFace embeddings (all-MiniLM-L6-v2) for memory with {config.get('llm_provider', 'unknown')} provider.")
                except Exception as e:
                    print(f"Warning: Failed to initialize HuggingFace embeddings: {e}. Memory features disabled.")
                    self.client = None
                    self.embedding_backend = None
            else:
                # No embedding backend available - disable memory
                print(f"Warning: No embedding backend available for {config.get('llm_provider', 'unknown')} provider. "
                      "Install sentence-transformers or set OPENAI_API_KEY to enable memory features.")
                self.client = None
                self.embedding_backend = None
        else:
            # Default to text-embedding-3-small for OpenAI and others
            self.embedding = "text-embedding-3-small"
            self.client = OpenAI(base_url=config["backend_url"])
            self.embedding_backend = "openai"

        self.chroma_client = chromadb.Client(Settings(allow_reset=True))
        self.situation_collection = self.chroma_client.get_or_create_collection(name=name)

    def get_embedding(self, text):
        """Get embedding for a text using the configured backend."""
        if self.client is None:
            raise RuntimeError("Embedding client not initialized. Check API key configuration.")

        if self.embedding_backend == "huggingface":
            # HuggingFace SentenceTransformer - returns numpy array or list
            embedding = self.client.encode(text)
            # Convert to list if needed
            if hasattr(embedding, 'tolist'):
                return embedding.tolist()
            return list(embedding)
        else:
            # OpenAI or Ollama - use OpenAI API format
            response = self.client.embeddings.create(
                model=self.embedding, input=text
            )
            return response.data[0].embedding

    def add_situations(self, situations_and_advice):
        """Add financial situations and their corresponding advice. Parameter is a list of tuples (situation, rec)"""

        situations = []
        advice = []
        ids = []
        embeddings = []

        offset = self.situation_collection.count()

        for i, (situation, recommendation) in enumerate(situations_and_advice):
            situations.append(situation)
            advice.append(recommendation)
            ids.append(str(offset + i))
            embeddings.append(self.get_embedding(situation))

        self.situation_collection.add(
            documents=situations,
            metadatas=[{"recommendation": rec} for rec in advice],
            embeddings=embeddings,
            ids=ids,
        )

    def get_memories(self, current_situation, n_matches=1):
        """Find matching recommendations using OpenAI embeddings"""
        try:
            # Skip if collection is empty
            if self.situation_collection.count() == 0:
                return []

            query_embedding = self.get_embedding(current_situation)

            results = self.situation_collection.query(
                query_embeddings=[query_embedding],
                n_results=n_matches,
                include=["metadatas", "documents", "distances"],
            )

            matched_results = []
            for i in range(len(results["documents"][0])):
                matched_results.append(
                    {
                        "matched_situation": results["documents"][0][i],
                        "recommendation": results["metadatas"][0][i]["recommendation"],
                        "similarity_score": 1 - results["distances"][0][i],
                    }
                )

            return matched_results
        except Exception as e:
            # Return empty if embedding fails (e.g., no OpenAI quota)
            print(f"Memory lookup skipped (embedding unavailable): {e}")
            return []


if __name__ == "__main__":
    # Example usage
    matcher = FinancialSituationMemory()

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
    matcher.add_situations(example_data)

    # Example query
    current_situation = """
    Market showing increased volatility in tech sector, with institutional investors 
    reducing positions and rising interest rates affecting growth stock valuations
    """

    try:
        recommendations = matcher.get_memories(current_situation, n_matches=2)

        for i, rec in enumerate(recommendations, 1):
            print(f"\nMatch {i}:")
            print(f"Similarity Score: {rec['similarity_score']:.2f}")
            print(f"Matched Situation: {rec['matched_situation']}")
            print(f"Recommendation: {rec['recommendation']}")

    except Exception as e:
        print(f"Error during recommendation: {str(e)}")
