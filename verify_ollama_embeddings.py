#!/usr/bin/env python3
"""
Verify that Ollama embeddings are working correctly.
This script tests the embedding endpoint and model availability.
"""

import os
import sys
from openai import OpenAI

def test_ollama_embeddings():
    """Test Ollama embeddings endpoint"""
    
    # Get configuration from environment or use defaults
    embedding_url = os.getenv("EMBEDDING_API_URL", "http://localhost:11434/v1")
    embedding_model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    
    print("=" * 60)
    print("Ollama Embeddings Verification")
    print("=" * 60)
    print(f"Embedding URL: {embedding_url}")
    print(f"Embedding Model: {embedding_model}")
    print()
    
    try:
        # Initialize OpenAI client pointing to Ollama
        client = OpenAI(
            base_url=embedding_url,
            api_key="ollama"  # Ollama doesn't require a real API key
        )
        
        # Test embedding generation
        test_text = "This is a test sentence for embedding generation."
        print(f"Testing embedding generation with text:")
        print(f"  '{test_text}'")
        print()
        
        response = client.embeddings.create(
            model=embedding_model,
            input=test_text
        )
        
        embedding = response.data[0].embedding
        
        print("✅ SUCCESS!")
        print(f"Generated embedding vector with {len(embedding)} dimensions")
        print(f"First 5 values: {embedding[:5]}")
        print()
        print("=" * 60)
        print("Ollama embeddings are working correctly! 🎉")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print("❌ FAILED!")
        print(f"Error: {str(e)}")
        print()
        print("=" * 60)
        print("Troubleshooting Steps:")
        print("=" * 60)
        print("1. Make sure Ollama is running:")
        print("   $ ollama serve")
        print()
        print("2. Pull the embedding model:")
        print(f"   $ ollama pull {embedding_model}")
        print()
        print("3. Verify Ollama is accessible:")
        print(f"   $ curl {embedding_url.replace('/v1', '')}/api/tags")
        print()
        print("4. Check if the model is available:")
        print(f"   $ ollama list | grep {embedding_model}")
        print()
        print("For more help, see: docs/LOCAL_EMBEDDINGS.md")
        print("=" * 60)
        
        return False

if __name__ == "__main__":
    success = test_ollama_embeddings()
    sys.exit(0 if success else 1)
