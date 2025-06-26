#!/usr/bin/env python3
"""
Test script to check OpenAI API connection for TradingAgents
"""

import os
import sys
from openai import OpenAI

def test_openai_connection():
    """Test if OpenAI API connection is working"""
    
    # Check if API key is set
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ OPENAI_API_KEY environment variable is not set!")
        print("\n🔧 To fix this, set your OpenAI API key:")
        print("   export OPENAI_API_KEY=your_api_key_here")
        print("\n📝 Or add it to your shell profile:")
        print("   echo 'export OPENAI_API_KEY=your_api_key_here' >> ~/.zshrc")
        print("   source ~/.zshrc")
        print("\n🔑 Get your API key from: https://platform.openai.com/api-keys")
        return False
    
    # Mask the API key for security (show only first 8 and last 4 characters)
    masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
    print(f"🔑 Found API key: {masked_key}")
    
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=api_key)
        
        # Make a simple test call
        print("🔄 Testing OpenAI API connection...")
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": "Hello! Please respond with just 'API connection successful'."}
            ],
            max_tokens=10,
            temperature=0
        )
        
        # Check response
        if response.choices and response.choices[0].message:
            message = response.choices[0].message.content.strip()
            print(f"✅ OpenAI API connection successful!")
            print(f"📨 Response: {message}")
            print(f"🎯 Model used: {response.model}")
            print(f"💰 Tokens used: {response.usage.total_tokens}")
            return True
        else:
            print("❌ Unexpected response format from OpenAI API")
            return False
            
    except Exception as e:
        print(f"❌ OpenAI API connection failed!")
        print(f"🚨 Error: {str(e)}")
        
        # Provide specific guidance based on error type
        error_str = str(e).lower()
        if "authentication" in error_str or "unauthorized" in error_str:
            print("\n🔧 This looks like an authentication error.")
            print("   Please check that your API key is correct and active.")
        elif "quota" in error_str or "billing" in error_str:
            print("\n🔧 This looks like a billing/quota error.")
            print("   Please check your OpenAI account billing and usage limits.")
        elif "rate" in error_str:
            print("\n🔧 This looks like a rate limiting error.")
            print("   Please wait a moment and try again.")
        else:
            print("\n🔧 Please check your internet connection and API key.")
            
        return False

def test_tradingagents_models():
    """Test if the models used by TradingAgents are available"""
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return False
        
    client = OpenAI(api_key=api_key)
    
    # Models used in TradingAgents default config
    models_to_test = [
        "gpt-4o-mini",  # quick_think_llm default
        "o1-mini",      # deep_think_llm default (o4-mini in config seems to be a typo)
    ]
    
    print("\n🧠 Testing TradingAgents model availability...")
    
    for model in models_to_test:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=5
            )
            print(f"   ✅ {model} - Available")
        except Exception as e:
            if "does not exist" in str(e).lower() or "not found" in str(e).lower():
                print(f"   ❌ {model} - Not available")
                if model == "o1-mini":
                    print(f"      💡 Try 'gpt-4o-mini' instead for both deep and quick thinking")
            else:
                print(f"   ⚠️  {model} - Error: {str(e)}")

if __name__ == "__main__":
    print("🤖 TradingAgents - OpenAI API Connection Test")
    print("=" * 50)
    
    # Test basic connection
    connection_ok = test_openai_connection()
    
    if connection_ok:
        # Test specific models
        test_tradingagents_models()
        
        print("\n🚀 OpenAI API is ready for TradingAgents!")
        print("\n💡 Next steps:")
        print("   1. Run the CLI: python -m cli.main")
        print("   2. Or test with code: python main.py")
    else:
        print("\n🛑 Please fix the API connection before using TradingAgents.")
        
    print("\n" + "=" * 50) 