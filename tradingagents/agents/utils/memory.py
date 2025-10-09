import chromadb
from chromadb.config import Settings
from openai import OpenAI
import numpy as np
import os
from langchain.text_splitter import RecursiveCharacterTextSplitter


class FinancialSituationMemory:
    def __init__(self, name, config, symbol=None, persistent_dir=None):
        if config["backend_url"] == "http://localhost:11434/v1":
            self.embedding = "nomic-embed-text"
        else:
            self.embedding = "text-embedding-3-small"
        
        # Get API key from config
        try:
            from ...dataflows.config import get_openai_api_key
            api_key = get_openai_api_key()
        except ImportError:
            api_key = None
            
        self.client = OpenAI(base_url=config["backend_url"], api_key=api_key)
        
        # Use persistent storage if directory is provided
        if persistent_dir:
            os.makedirs(persistent_dir, exist_ok=True)
            
            # Use PersistentClient for disk storage
            chroma_settings = Settings(
                anonymized_telemetry=False,
                allow_reset=True,
                is_persistent=True
            )
            
            try:
                self.chroma_client = chromadb.PersistentClient(
                    path=persistent_dir,
                    settings=chroma_settings
                )
            except Exception:
                # Fallback: try without settings if there are compatibility issues
                self.chroma_client = chromadb.PersistentClient(path=persistent_dir)
        else:
            # Use in-memory client for backward compatibility
            self.chroma_client = chromadb.Client(Settings(allow_reset=True))
        
        # Create collection name
        if symbol:
            collection_name = f"{name}_{symbol}"
        else:
            collection_name = name
        
        # Sanitize collection name (ChromaDB requires alphanumeric, underscore, hyphen)
        collection_name = collection_name.replace(' ', '_').replace('.', '_')
        
        # Try to get existing collection or create new one
        try:
            self.situation_collection = self.chroma_client.get_collection(name=collection_name)
        except:
            self.situation_collection = self.chroma_client.create_collection(name=collection_name)

    def get_embedding(self, text):
        """Get OpenAI embeddings for a text, using RecursiveCharacterTextSplitter for long texts.
        
        Returns:
            list: List of embeddings (one per chunk). If text is short, returns list with single embedding.
        """
        # text-embedding-3-small has a max context length of 8192 tokens
        # Conservative estimate: ~3 characters per token for safety margin
        max_chars = 24000  # ~8000 tokens * 3 chars/token
        
        if len(text) <= max_chars:
            # Text is short enough, get embedding directly
            response = self.client.embeddings.create(
                model=self.embedding, input=text
            )
            return [response.data[0].embedding]
        
        # Text is too long, use RecursiveCharacterTextSplitter
        print(f"Text length {len(text)} exceeds limit, splitting into chunks for embedding")
        
        # Use RecursiveCharacterTextSplitter for intelligent chunking
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chars - 1000,  # Leave some buffer
            chunk_overlap=500,  # Overlap to preserve context
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]  # Try to split at natural boundaries
        )
        
        chunks = text_splitter.split_text(text)
        print(f"Split text into {len(chunks)} chunks for embedding")
        
        # Get embeddings for all chunks
        chunk_embeddings = []
        for i, chunk in enumerate(chunks):
            try:
                response = self.client.embeddings.create(
                    model=self.embedding, input=chunk
                )
                chunk_embeddings.append(response.data[0].embedding)
            except Exception as e:
                print(f"Failed to get embedding for chunk {i}: {e}")
                continue
        
        if not chunk_embeddings:
            raise ValueError("Failed to get embeddings for any chunks")
        
        return chunk_embeddings

    def add_situations(self, situations_and_advice):
        """Add financial situations and their corresponding advice. Parameter is a list of tuples (situation, rec)"""

        situations = []
        advice = []
        ids = []
        embeddings = []

        offset = self.situation_collection.count()
        current_id = offset

        for situation, recommendation in situations_and_advice:
            # Get embeddings (returns list of embeddings for chunks)
            situation_embeddings = self.get_embedding(situation)
            
            # Add each chunk as a separate document
            for chunk_idx, embedding in enumerate(situation_embeddings):
                situations.append(situation)  # Store full situation for each chunk
                advice.append(recommendation)
                ids.append(str(current_id))
                embeddings.append(embedding)
                current_id += 1

        self.situation_collection.add(
            documents=situations,
            metadatas=[{"recommendation": rec} for rec in advice],
            embeddings=embeddings,
            ids=ids,
        )

    def get_memories(self, current_situation, n_matches=1):
        """Find matching recommendations using OpenAI embeddings"""
        # Get embeddings (returns list)
        query_embeddings = self.get_embedding(current_situation)
        
        # Average embeddings if multiple chunks
        if len(query_embeddings) > 1:
            query_embedding = np.mean(query_embeddings, axis=0).tolist()
        else:
            query_embedding = query_embeddings[0]

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
