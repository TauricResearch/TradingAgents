import os
import chromadb
from chromadb.config import Settings
from openai import OpenAI


class FinancialSituationMemory:
    def __init__(self, name, config):
        # Check if user explicitly set EMBEDDING_API_URL - if so, use it regardless of provider
        embedding_url = os.getenv("EMBEDDING_API_URL")
        
        if embedding_url:
            # User has explicitly configured embedding service URL
            self.embedding = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
            self.client = OpenAI(
                base_url=embedding_url,
                api_key=os.getenv("EMBEDDING_API_KEY", "local")
            )
        elif config.get("llm_provider") == "google":
            self.embedding = "text-embedding-004"
            
            google_api_key = os.getenv("GOOGLE_API_KEY")
            if not google_api_key:
                raise ValueError("❌ GOOGLE_API_KEY not found in environment. Please add it to your .env file or export it.")
                
            # Use Google's OpenAI-compatible endpoint with retries
            self.client = OpenAI(
                api_key=google_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                max_retries=5
            )
        elif config.get("llm_provider") == "anthropic":
            # Anthropic doesn't provide embeddings - default to local embedding service
            self.embedding = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
            self.client = OpenAI(
                base_url="http://localhost:8000/v1",
                api_key="local"
            )
        elif config["backend_url"] == "http://localhost:11434/v1" or config.get("llm_provider") == "ollama":
            self.embedding = "nomic-embed-text"
            self.client = OpenAI(base_url=config["backend_url"])
        else:
            self.embedding = "text-embedding-3-small"
            self.client = OpenAI(base_url=config["backend_url"])
            
        self.chroma_client = chromadb.Client(Settings(allow_reset=True))
        self.situation_collection = self.chroma_client.create_collection(name=name)

    def get_embedding(self, text):
        """Get OpenAI embedding for a text"""
        
        # DEBUG: Check API Key
        if hasattr(self, 'client') and self.client.api_key:
             masked_key = self.client.api_key[:4] + "..."
             # print(f"DEBUG: Using API Key: {masked_key}")
        
        # Truncate text if too long
        # Configurable via EMBEDDING_TRUNCATION_LIMIT (default 1000 for local models)
        # Set to -1 or 0 to disable truncation.
        try:
            truncation_limit = int(os.getenv("EMBEDDING_TRUNCATION_LIMIT", "1000"))
        except ValueError:
            truncation_limit = 1000

        if truncation_limit > 0 and len(text) > truncation_limit:
             # print(f"WARNING: Truncating text for embedding. Length {len(text)} > {truncation_limit}")
             text = text[:truncation_limit]
        
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


    def clear(self):
        """Clear the memory by deleting and recreating the collection."""
        try:
             self.chroma_client.delete_collection(self.situation_collection.name)
             self.situation_collection = self.chroma_client.create_collection(name=self.situation_collection.name)
        except Exception as e:
             print(f"Warning: Failed to clear memory {self.situation_collection.name}: {e}")

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
