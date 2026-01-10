#!/usr/bin/env python3
"""
Verify that local sentence-transformers embeddings are working correctly.
This script tests the local embedding model without requiring external services.
"""

import os
import sys

def test_local_embeddings():
    """Test local sentence-transformers embeddings"""
    
    embedding_model = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    
    print("=" * 60)
    print("Local Embeddings Verification (sentence-transformers)")
    print("=" * 60)
    print(f"Embedding Model: {embedding_model}")
    print()
    
    try:
        # 1. Try to import sentence-transformers (Local Library Mode)
        try:
            from sentence_transformers import SentenceTransformer
            print("✅ Found local sentence-transformers library.")
            
            # Load the model
            print(f"📦 Loading embedding model: {embedding_model}")
            print("   (First run will download the model, ~90MB)")
            print()
            
            model = SentenceTransformer(embedding_model)
            
            # Test embedding generation
            test_texts = [
                "This is a test sentence for embedding generation.",
                "Financial markets are showing increased volatility.",
                "The company reported strong quarterly earnings."
            ]
            
            print(f"Testing embedding generation with {len(test_texts)} sentences:")
            for i, text in enumerate(test_texts, 1):
                print(f"  {i}. '{text[:50]}...'")
            print()
            
            embeddings = model.encode(test_texts, convert_to_numpy=True)
            
            print("✅ SUCCESS!")
            print(f"Generated {len(embeddings)} embedding vectors")
            print(f"Embedding dimensions: {embeddings.shape[1]}")
            print(f"First embedding (first 5 values): {embeddings[0][:5].tolist()}")
            print()
            
            # Test similarity
            from numpy import dot
            from numpy.linalg import norm
            
            def cosine_similarity(a, b):
                return dot(a, b) / (norm(a) * norm(b))
            
            sim_0_1 = cosine_similarity(embeddings[0], embeddings[1])
            sim_1_2 = cosine_similarity(embeddings[1], embeddings[2])
            
            print("Similarity scores:")
            print(f"  Sentence 1 ↔ Sentence 2: {sim_0_1:.4f}")
            print(f"  Sentence 2 ↔ Sentence 3: {sim_1_2:.4f}")
            print()
            
            print("=" * 60)
            print("Local embeddings (Library) are working correctly! 🎉")
            print("=" * 60)
            return True

        except ImportError:
            # 2. If Library missing, try connection to Local Service (Docker Mode)
            print("ℹ️  sentence-transformers library not installed.")
            print("Checking for local embedding service...")
            
            try:
                from openai import OpenAI
                
                embedding_url = os.getenv("EMBEDDING_API_URL", "http://localhost:8000/v1")
                print(f"Connecting to: {embedding_url}")
                
                client = OpenAI(base_url=embedding_url, api_key="local")
                
                # Test embedding generation via API
                test_texts = [
                    "This is a test sentence for embedding generation.",
                    "Financial markets are showing increased volatility.",
                    "The company reported strong quarterly earnings."
                ]
                
                print(f"Testing embedding generation via API with {len(test_texts)} sentences:")
                for i, text in enumerate(test_texts, 1):
                    print(f"  {i}. '{text[:50]}...'")
                print()
                
                response = client.embeddings.create(model=embedding_model, input=test_texts)
                embeddings = [data.embedding for data in response.data]
                
                print("✅ SUCCESS!")
                print(f"Generated {len(embeddings)} embedding vectors via API")
                print(f"Embedding dimensions: {len(embeddings[0])}")
                print(f"First embedding (first 5 values): {embeddings[0][:5]}")
                print()
                
                print("=" * 60)
                print("Local embedding service (Docker) is working correctly! 🎉")
                print("=" * 60)
                return True
                
            except Exception as service_error:
                print("❌ FAILED!")
                print("Neither sentence-transformers library nor local embedding service found.")
                print(f"Library Error: sentence-transformers not installed")
                print(f"Service Error: {str(service_error)}")
                print()
                print("=" * 60)
                print("Installation Options:")
                print("=" * 60)
                print("OPTION 1: Run Service (Recommended - Docker)")
                print("   docker run -d -p 8000:8000 ghcr.io/huggingface/text-embeddings-inference:cpu-latest --model-id sentence-transformers/all-MiniLM-L6-v2")
                print("   export EMBEDDING_API_URL=http://localhost:8000/v1")
                print()
                print("OPTION 2: Install Library (Runs locally, adds dependencies)")
                print("   pip install sentence-transformers")
                print("=" * 60)
                return False

    except Exception as e:
        print("❌ FAILED!")
        print(f"Error: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_local_embeddings()
    sys.exit(0 if success else 1)
