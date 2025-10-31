import chromadb
from chromadb.config import Settings
from openai import OpenAI
import os


class FinancialSituationMemory:
    def __init__(self, name, config):
        self.provider = config.get("llm_provider", "openai").lower()
        
        # Determine embedding model based on provider
        if self.provider == "ollama":
            self.embedding = "nomic-embed-text"
            self.use_ollama_embeddings = True
        elif config.get("backend_url") == "http://localhost:11434/v1":
            self.embedding = "nomic-embed-text"
            self.use_ollama_embeddings = True
        else:
            self.embedding = "text-embedding-3-small"
            self.use_ollama_embeddings = False
        
        # Only create OpenAI client if we're using OpenAI embeddings
        if not self.use_ollama_embeddings:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self.client = OpenAI(base_url=config.get("backend_url"), api_key=api_key)
            else:
                self.client = OpenAI(base_url=config.get("backend_url"))
        else:
            self.client = None
            
        self.chroma_client = chromadb.Client(Settings(allow_reset=True))
        self.situation_collection = self.chroma_client.create_collection(name=name)

    def get_embedding(self, text):
        """Get embedding for text - provider agnostic"""
        
        if self.use_ollama_embeddings:
            # For Ollama, use chromadb's built-in embedding function
            # or return None to let chromadb handle it
            # ChromaDB will use its default embedding function
            return None
        else:
            # Use OpenAI embeddings
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
            embedding = self.get_embedding(situation)
            if embedding is not None:
                embeddings.append(embedding)

        # Add to collection - chromadb will use default embeddings if none provided
        add_params = {
            "documents": situations,
            "metadatas": [{"recommendation": rec} for rec in advice],
            "ids": ids,
        }
        
        if embeddings:  # Only add embeddings if we have them
            add_params["embeddings"] = embeddings
            
        self.situation_collection.add(**add_params)

    def get_memories(self, current_situation, n_matches=1):
        """Find matching recommendations using embeddings"""
        query_embedding = self.get_embedding(current_situation)

        # Build query parameters
        query_params = {
            "n_results": n_matches,
            "include": ["metadatas", "documents", "distances"],
        }
        
        if query_embedding is not None:
            query_params["query_embeddings"] = [query_embedding]
        else:
            # Use text-based search if no embeddings
            query_params["query_texts"] = [current_situation]

        results = self.situation_collection.query(**query_params)

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
