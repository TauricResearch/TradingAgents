#!/usr/bin/env python3
"""Test script to verify Google API connectivity and model availability."""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

# Load environment variables
load_dotenv()

def test_google_api():
    """Test Google API with different models via local proxy."""
    
    # Use local proxy
    proxy_url = "http://localhost:8080"
    
    print(f"🔧 Using proxy: {proxy_url}")
    
    # Test models
    test_models = [
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-exp",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
        "gemini-3-flash-preview",
        "gemini-3-pro-preview",
    ]
    
    for model_name in test_models:
        print(f"\n{'='*60}")
        print(f"Testing model: {model_name}")
        print(f"{'='*60}")
        
        try:
            # Initialize client
            print(f"🔧 Initializing {model_name}...")
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                max_retries=3,
                base_url="http://localhost:8080",
                request_timeout=30
            )
            
            # Test simple query
            print(f"📤 Sending test query...")
            response = llm.invoke("Say 'Hello, I am working!' in exactly 5 words.")
            
            print(f"✅ SUCCESS!")
            print(f"📥 Response: {response.content}")
            
        except Exception as e:
            print(f"❌ FAILED: {type(e).__name__}")
            print(f"   Error: {str(e)[:200]}")
            
            # Check for specific error types
            if "404" in str(e):
                print(f"   → Model '{model_name}' not found or not available")
            elif "403" in str(e) or "401" in str(e):
                print(f"   → Authentication error - check API key permissions")
            elif "429" in str(e):
                print(f"   → Rate limit exceeded")
            elif "timeout" in str(e).lower():
                print(f"   → Request timed out")

if __name__ == "__main__":
    print("🚀 Google API Test Script")
    print("="*60)
    test_google_api()
    print("\n" + "="*60)
    print("✅ Test complete!")
