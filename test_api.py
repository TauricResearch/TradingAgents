#!/usr/bin/env python3
"""Quick test to verify OpenAI API is working"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_openai():
    """Test OpenAI API connectivity"""
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        print("❌ No OpenAI API key found")
        return False

    print(f"✅ OpenAI API Key found: {api_key[:20]}...")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        # Test with a simple completion
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say 'API working!'"}],
            max_tokens=10
        )

        result = response.choices[0].message.content
        print(f"✅ OpenAI API Response: {result}")
        return True

    except Exception as e:
        print(f"❌ OpenAI API Error: {e}")
        return False

if __name__ == "__main__":
    print("Testing OpenAI API...")
    test_openai()