import chromadb
from chromadb.config import Settings
from openai import OpenAI
import uuid
import time


class FinancialSituationMemory:
    def __init__(self, name, config, session_id=None):
        if config["backend_url"] == "http://localhost:11434/v1":
            self.embedding = "nomic-embed-text"
        else:
            self.embedding = "text-embedding-3-small"
        self.openai_client = OpenAI(base_url=config["backend_url"])
        
        # Generate session ID if not provided 
        if session_id is None:
            session_id = str(uuid.uuid4())
        self.session_id = session_id
        self.collection_name = f"{name}_{session_id}"
        
        # Initialize ChromaDB client
        chroma_path = config.get("chroma_db_path", "./chroma_db")
        settings = Settings(allow_reset=True)
        self.chroma_client = chromadb.PersistentClient(path=chroma_path, settings=settings)
        
        # Get or create collection to avoid conflicts
        self.situation_collection = self._get_or_create_collection()

    def _get_or_create_collection(self):
        """Get existing collection or create new one to avoid conflicts"""
        try:
            return self.chroma_client.get_collection(name=self.collection_name)
        except Exception:
            return self.chroma_client.create_collection(name=self.collection_name)

    def get_embedding(self, text):
        """Get OpenAI embedding for a text"""
        
        response = self.openai_client.embeddings.create(
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

    def cleanup(self):
        """
        Clean up the collection (optional - for resource management).
        This method can be called to remove the collection when no longer needed.
        """
        try:
            self.chroma_client.delete_collection(self.collection_name)
        except Exception:
            pass


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
