import os
import chromadb
from chromadb.config import Settings


class FinancialSituationMemory:
    def __init__(self, name, config):
        """
        Initialize the memory with configurable embedding provider.
        
        Config options:
            embedding_provider: "local" (default) or "openai"
            embedding_model: Model name for the embedding provider
                - For local: "all-MiniLM-L6-v2" (default), "all-mpnet-base-v2", etc.
                - For OpenAI: "text-embedding-3-small" (default), "text-embedding-3-large", etc.
            embedding_base_url: Base URL for OpenAI-compatible API (only used when provider is "openai")
            embedding_api_key: API key for OpenAI (only used when provider is "openai")
        """
        self.provider = config.get("embedding_provider", "local").lower()
        
        if self.provider == "local":
            self._init_local_embedding(config)
        elif self.provider == "openai":
            self._init_openai_embedding(config)
        else:
            raise ValueError(f"Unsupported embedding provider: {self.provider}. Use 'local' or 'openai'.")
        
        self.chroma_client = chromadb.Client(Settings(allow_reset=True))
        self.situation_collection = self.chroma_client.get_or_create_collection(name=name)

    def _init_local_embedding(self, config):
        """Initialize local embedding using sentence-transformers."""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for local embeddings. "
                "Install it with: pip install sentence-transformers"
            )
        
        # Default to all-MiniLM-L6-v2 - a lightweight and efficient model
        model_name = config.get("embedding_model", "all-MiniLM-L6-v2")
        
        import logging
        logging.info(f"Loading local embedding model: {model_name}")
        
        self.model = SentenceTransformer(model_name)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        
        logging.info(f"Local embedding model loaded. Dimension: {self.embedding_dim}")

    def _init_openai_embedding(self, config):
        """Initialize OpenAI embedding client."""
        from openai import OpenAI
        
        self.embedding_model = config.get("embedding_model", "text-embedding-3-small")
        
        # Get embedding configuration from config, with fallbacks
        embedding_base_url = config.get("embedding_base_url", "https://api.openai.com/v1")
        embedding_api_key = config.get("embedding_api_key")
        
        # Fallback chain for API key
        if not embedding_api_key:
            # Try environment variable first
            embedding_api_key = os.getenv("OPENAI_API_KEY")
            if not embedding_api_key:
                # Fall back to LLM keys as last resort
                embedding_api_key = config.get("quick_think_api_key") or config.get("deep_think_api_key")
                if embedding_api_key:
                    import logging
                    logging.warning("Using LLM API key for embeddings. Consider setting embedding_api_key or OPENAI_API_KEY.")
        
        if not embedding_api_key:
            raise ValueError(
                "OpenAI API key is required for OpenAI embeddings. "
                "Set 'embedding_api_key' in config or OPENAI_API_KEY environment variable, "
                "or use 'embedding_provider': 'local' for local embeddings without API key."
            )
        
        # Use configured endpoint for embeddings
        self.client = OpenAI(base_url=embedding_base_url, api_key=embedding_api_key)

    def get_embedding(self, text):
        """Get embedding for a text using the configured provider."""
        # Truncate text to avoid exceeding embedding model's token limit
        max_chars = 4000
        if len(text) > max_chars:
            text = text[:max_chars]
        
        if self.provider == "local":
            return self._get_local_embedding(text)
        else:
            return self._get_openai_embedding(text)

    def _get_local_embedding(self, text):
        """Get embedding using local sentence-transformers model."""
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def _get_openai_embedding(self, text):
        """Get embedding using OpenAI API."""
        response = self.client.embeddings.create(
            model=self.embedding_model, input=text
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
        """Find matching recommendations using embeddings"""
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


if __name__ == "__main__":
    # Example usage with local embedding (no API key required!)
    config = {
        "embedding_provider": "local",  # Use local model, no API key needed
        "embedding_model": "all-MiniLM-L6-v2",  # Lightweight and efficient
    }
    
    matcher = FinancialSituationMemory("test_memory", config)

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
    print("Adding example situations...")
    matcher.add_situations(example_data)
    print("Done!")

    # Example query
    current_situation = """
    Market showing increased volatility in tech sector, with institutional investors 
    reducing positions and rising interest rates affecting growth stock valuations
    """

    try:
        print("\nSearching for recommendations...")
        recommendations = matcher.get_memories(current_situation, n_matches=2)

        for i, rec in enumerate(recommendations, 1):
            print(f"\nMatch {i}:")
            print(f"Similarity Score: {rec['similarity_score']:.2f}")
            print(f"Matched Situation: {rec['matched_situation']}")
            print(f"Recommendation: {rec['recommendation']}")

    except Exception as e:
        print(f"Error during recommendation: {str(e)}")
