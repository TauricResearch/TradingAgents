#!/usr/bin/env python3
"""
AI Provider Connectivity Test for TradingAgents
This script tests which AI providers are accessible from your network.
"""

import os
import requests
import json
from pathlib import Path

def load_env_file():
    """Load environment variables from .env file"""
    env_file = Path('.env')
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value

def test_anthropic_api():
    """Test Anthropic Claude API"""
    print("🤖 Testing Anthropic (Claude) API...")
    
    api_key = os.environ.get('ANTHROPIC_API_KEY', 'test-key')
    if api_key == 'your_anthropic_api_key_here':
        print("   ⚠️  Please set your ANTHROPIC_API_KEY in .env file")
        api_key = 'test-key'
    
    try:
        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01'
            },
            json={
                'model': 'claude-3-5-haiku-20241022',
                'max_tokens': 10,
                'messages': [{'role': 'user', 'content': 'Hello, respond with just "OK"'}]
            },
            timeout=15
        )
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ SUCCESS! Claude responded: {result['content'][0]['text']}")
            return True
        elif response.status_code == 401:
            print("   ⚠️  API accessible but invalid API key")
            return "accessible"
        else:
            print(f"   ❌ Unexpected response: {response.text[:100]}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Connection failed: {e}")
        return False

def test_google_api():
    """Test Google Generative AI API"""
    print("\n🧠 Testing Google (Gemini) API...")
    
    api_key = os.environ.get('GOOGLE_API_KEY', 'test-key')
    if api_key == 'your_google_api_key_here':
        print("   ⚠️  Please set your GOOGLE_API_KEY in .env file")
        api_key = 'test-key'
    
    try:
        response = requests.post(
            f'https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={api_key}',
            headers={'Content-Type': 'application/json'},
            json={
                'contents': [{'parts': [{'text': 'Hello, respond with just "OK"'}]}]
            },
            timeout=15
        )
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            text = result['candidates'][0]['content']['parts'][0]['text']
            print(f"   ✅ SUCCESS! Gemini responded: {text}")
            return True
        elif response.status_code in [400, 403]:
            print("   ⚠️  API accessible but invalid/missing API key")
            return "accessible"
        else:
            print(f"   ❌ Unexpected response: {response.text[:100]}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Connection failed: {e}")
        return False

def test_langchain_integration():
    """Test if the AI providers work with LangChain (TradingAgents backend)"""
    print("\n🔗 Testing LangChain Integration...")
    
    try:
        # Test Anthropic with LangChain
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if api_key and api_key != 'your_anthropic_api_key_here':
            from langchain_anthropic import ChatAnthropic
            
            llm = ChatAnthropic(
                model="claude-3-5-haiku-20241022",
                api_key=api_key,
                max_tokens=10
            )
            
            response = llm.invoke("Hello, respond with just 'LangChain OK'")
            print(f"   ✅ Anthropic + LangChain: {response.content}")
            return True
        else:
            print("   ⚠️  No valid Anthropic API key for LangChain test")
            return False
            
    except Exception as e:
        print(f"   ❌ LangChain integration failed: {e}")
        return False

def test_ollama_local():
    """Test local Ollama installation"""
    print("\n🏠 Testing Ollama (Local AI)...")
    
    try:
        # Override proxy settings for local connection
        session = requests.Session()
        session.trust_env = False
        
        response = session.get('http://localhost:11434/api/tags', timeout=5)
        
        if response.status_code == 200:
            models = response.json().get('models', [])
            print(f"   ✅ Ollama running with {len(models)} models:")
            for model in models[:3]:
                print(f"      - {model.get('name', 'Unknown')}")
            return True
        else:
            print(f"   ❌ Ollama responding but status: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Ollama not accessible: {e}")
        print("   💡 To install: brew install ollama && ollama serve")
        return False

def main():
    """Run all tests and provide recommendations"""
    print("🧪 TradingAgents AI Provider Test Suite")
    print("=" * 50)
    
    # Load environment variables
    load_env_file()
    
    # Run tests
    anthropic_result = test_anthropic_api()
    google_result = test_google_api()
    ollama_result = test_ollama_local()
    
    if anthropic_result == True:
        langchain_result = test_langchain_integration()
    else:
        langchain_result = False
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 50)
    
    if anthropic_result == True:
        print("✅ Anthropic (Claude) - FULLY WORKING")
        print("   🎯 RECOMMENDED: Use this for TradingAgents!")
    elif anthropic_result == "accessible":
        print("⚠️  Anthropic (Claude) - Accessible but need valid API key")
        print("   🔑 Get key from: https://console.anthropic.com/")
    else:
        print("❌ Anthropic (Claude) - Not accessible")
    
    if google_result == True:
        print("✅ Google (Gemini) - FULLY WORKING")
    elif google_result == "accessible":
        print("⚠️  Google (Gemini) - Accessible but need valid API key")
    else:
        print("❌ Google (Gemini) - Blocked by company network")
    
    if ollama_result:
        print("✅ Ollama (Local) - Available")
        print("   💰 FREE option, runs on your machine")
    else:
        print("❌ Ollama (Local) - Not installed/running")
    
    print("\n🚀 NEXT STEPS:")
    if anthropic_result:
        print("1. Get Anthropic API key if you haven't already")
        print("2. Update ANTHROPIC_API_KEY in .env file")
        print("3. Run TradingAgents and select 'Anthropic' as provider")
    elif ollama_result:
        print("1. Use Ollama (local) as your AI provider")
        print("2. Run TradingAgents and select 'Ollama' as provider") 
    else:
        print("1. Consider installing Ollama for local AI")
        print("2. Or try getting API keys for accessible providers")

if __name__ == "__main__":
    main() 