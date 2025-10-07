#!/usr/bin/env python3
"""Test script to verify TradingAgents setup and API connectivity"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_api_keys():
    """Check if required API keys are set"""
    print("🔍 Checking API Keys...")

    alpha_vantage_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    status = {}

    if alpha_vantage_key and alpha_vantage_key != "alpha_vantage_api_key_placeholder":
        print("✅ Alpha Vantage API Key: SET")
        status["alpha_vantage"] = True
    else:
        print("❌ Alpha Vantage API Key: NOT SET or using placeholder")
        status["alpha_vantage"] = False

    if openai_key and openai_key != "openai_api_key_placeholder":
        print("✅ OpenAI API Key: SET")
        status["openai"] = True
    else:
        print("❌ OpenAI API Key: NOT SET or using placeholder")
        status["openai"] = False

    return status

def test_imports():
    """Test if all required packages can be imported"""
    print("\n🔍 Testing Package Imports...")

    packages = [
        "langchain_openai",
        "langchain_experimental",
        "pandas",
        "yfinance",
        "langgraph",
        "tradingagents"
    ]

    failed = []
    for package in packages:
        try:
            __import__(package)
            print(f"✅ {package}: OK")
        except ImportError as e:
            print(f"❌ {package}: FAILED - {e}")
            failed.append(package)

    return len(failed) == 0

def test_alpha_vantage_connection():
    """Test Alpha Vantage API connectivity"""
    print("\n🔍 Testing Alpha Vantage API...")

    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key or api_key == "alpha_vantage_api_key_placeholder":
        print("⏭️  Skipping Alpha Vantage test - API key not set")
        return False

    try:
        import requests
        # Test with a simple quote endpoint
        url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=AAPL&apikey={api_key}"
        response = requests.get(url, timeout=10)
        data = response.json()

        if "Global Quote" in data:
            print("✅ Alpha Vantage API: Connected successfully")
            return True
        elif "Note" in data:
            print("⚠️  Alpha Vantage API: Rate limit reached")
            return True
        elif "Error Message" in data:
            print(f"❌ Alpha Vantage API: {data['Error Message']}")
            return False
        else:
            print("❌ Alpha Vantage API: Unexpected response")
            return False
    except Exception as e:
        print(f"❌ Alpha Vantage API: Connection failed - {e}")
        return False

def test_yfinance():
    """Test yfinance data fetching"""
    print("\n🔍 Testing yfinance...")

    try:
        import yfinance as yf
        ticker = yf.Ticker("AAPL")
        info = ticker.info
        if info and "symbol" in info:
            print("✅ yfinance: Working correctly")
            return True
        else:
            print("❌ yfinance: Failed to fetch data")
            return False
    except Exception as e:
        print(f"❌ yfinance: Error - {e}")
        return False

def main():
    print("=" * 60)
    print("🚀 TradingAgents Setup Test")
    print("=" * 60)

    # Check API keys
    api_status = check_api_keys()

    # Test imports
    imports_ok = test_imports()

    # Test connections if keys are available
    if api_status["alpha_vantage"]:
        test_alpha_vantage_connection()

    test_yfinance()

    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)

    if not api_status["openai"]:
        print("\n⚠️  IMPORTANT: You need to set your OpenAI API key!")
        print("   Either:")
        print("   1. Add it to the .env file")
        print("   2. Export it: export OPENAI_API_KEY='your-key-here'")

    if imports_ok and api_status["alpha_vantage"]:
        print("\n✅ Basic setup is complete!")
        print("\n📝 Next steps:")
        if not api_status["openai"]:
            print("1. Add your OpenAI API key")
            print("2. Run: python main.py")
            print("   OR")
            print("   python -m cli.main")
        else:
            print("1. Run: python main.py")
            print("   OR")
            print("   python -m cli.main")
    else:
        print("\n❌ Setup incomplete. Please fix the issues above.")

if __name__ == "__main__":
    main()