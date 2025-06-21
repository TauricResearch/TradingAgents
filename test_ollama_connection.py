#!/usr/bin/env python3
"""
Simple test script to verify Ollama connection is working.
"""

import os
import requests
import time
from openai import OpenAI

def test_ollama_connection():
    """Test if Ollama is accessible and responding."""
    
    # Get configuration from environment
    backend_url = os.environ.get("LLM_BACKEND_URL", "http://localhost:11434/v1")
    model = os.environ.get("LLM_DEEP_THINK_MODEL", "qwen3:0.6b")
    embedding_model = os.environ.get("LLM_EMBEDDING_MODEL", "nomic-embed-text")
    
    print(f"Testing Ollama connection:")
    print(f"  Backend URL: {backend_url}")
    print(f"  Model: {model}")
    print(f"  Embedding Model: {embedding_model}")
    
    # Test 1: Check if Ollama API is responding
    try:
        response = requests.get(f"{backend_url.replace('/v1', '')}/api/tags", timeout=10)
        if response.status_code == 200:
            print("✅ Ollama API is responding")
        else:
            print(f"❌ Ollama API returned status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Failed to connect to Ollama API: {e}")
        return False
    
    # Test 2: Check if the model is available
    try:
        response = requests.get(f"{backend_url.replace('/v1', '')}/api/tags", timeout=10)
        models = response.json().get("models", [])
        model_names = [m.get("name", "") for m in models]
        
        if any(name.startswith(model) for name in model_names):
            print(f"✅ Model '{model}' is available")
        else:
            print(f"❌ Model '{model}' not found. Available models: {model_names}")
            return False
    except Exception as e:
        print(f"❌ Failed to check model availability: {e}")
        return False
    
    # Test 3: Test OpenAI-compatible API
    try:
        client = OpenAI(base_url=backend_url, api_key="dummy")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hello, say 'test successful'"}],
            max_tokens=50
        )
        print("✅ OpenAI-compatible API is working")
        print(f"   Response: {response.choices[0].message.content}")
        return True
    except Exception as e:
        print(f"❌ OpenAI-compatible API test failed: {e}")
        return False
    
    # Test 4: Check if the embedding model is available
    try:
        response = requests.get(f"{api_url}/api/tags", timeout=10)
        models = response.json().get("models", [])
        model_names = [m.get("name") for m in models if m.get("name")]
        
        # Check if any of the available models starts with the embedding model name
        if any(name.startswith(embedding_model) for name in model_names):
            print(f"✅ Embedding Model '{embedding_model}' is available")
        else:
            print(f"❌ Embedding Model '{embedding_model}' not found. Available models: {model_names}")
            return False
    except Exception as e:
        print(f"❌ Failed to check embedding model availability: {e}")
        return False

    # Test 5: Test OpenAI-compatible embedding API
    try:
        client = OpenAI(base_url=backend_url, api_key="dummy")
        response = client.embeddings.create(
            model=embedding_model,
            input="This is a test sentence.",
            encoding_format="float"
        )
        if response.data and len(response.data) > 0 and response.data[0].embedding:
            print("✅ OpenAI-compatible embedding API is working")
            print(f"   Successfully generated embedding of dimension: {len(response.data[0].embedding)}")
            return True
        else:
            print("❌ Embedding API test failed: No embedding data in response")
            return False
    except Exception as e:
        print(f"❌ OpenAI-compatible embedding API test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_ollama_connection()
    if success:
        print("\n🎉 All tests passed! Ollama is ready.")
        exit(0)
    else:
        print("\n💥 Tests failed! Check Ollama configuration.")
        exit(1) 