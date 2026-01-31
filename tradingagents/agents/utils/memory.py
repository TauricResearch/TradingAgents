import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions


class FinancialSituationMemory:
    """Memory system for storing and retrieving financial situations using local embeddings."""

    def __init__(self, name, config):
        """
        Initialize the memory system with local embeddings.

        Args:
            name: Name for the ChromaDB collection
            config: Configuration dictionary (kept for compatibility)
        """
        # Use ChromaDB's default embedding function (uses all-MiniLM-L6-v2 internally)
        self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        self.chroma_client = chromadb.Client(Settings(allow_reset=True))
        # Use get_or_create to avoid errors when collection already exists
        self.situation_collection = self.chroma_client.get_or_create_collection(
            name=name,
            embedding_function=self.embedding_fn
        )

    def get_embedding(self, text):
        """Get embedding for a text using the embedding function."""
        embeddings = self.embedding_fn([text])
        return embeddings[0]

    def add_situations(self, situations_and_advice):
        """Add financial situations and their corresponding advice. Parameter is a list of tuples (situation, rec)"""

        situations = []
        advice = []
        ids = []

        offset = self.situation_collection.count()

        for i, (situation, recommendation) in enumerate(situations_and_advice):
            situations.append(situation)
            advice.append(recommendation)
            ids.append(str(offset + i))

        # Let ChromaDB handle embeddings automatically
        self.situation_collection.add(
            documents=situations,
            metadatas=[{"recommendation": rec} for rec in advice],
            ids=ids,
        )

    def get_memories(self, current_situation, n_matches=1):
        """Find matching recommendations using embeddings"""
        results = self.situation_collection.query(
            query_texts=[current_situation],
            n_results=n_matches,
            include=["metadatas", "documents", "distances"],
        )

        matched_results = []
        if results["documents"] and results["documents"][0]:
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
    # Example usage
    matcher = FinancialSituationMemory("test_memory", {})

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
