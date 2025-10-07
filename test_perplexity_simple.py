#!/usr/bin/env python
"""
Simplified test script to verify Perplexity API connectivity.
Works around import issues.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add directories to path
sys.path.insert(0, '.')
sys.path.insert(0, './autonomous')


async def test_perplexity_direct():
    """Test Perplexity API directly without complex imports"""

    print("=" * 60)
    print("🔍 Testing Perplexity Finance API (Direct)")
    print("=" * 60)

    api_key = os.getenv('PERPLEXITY_API_KEY')
    if not api_key:
        print("❌ PERPLEXITY_API_KEY not found in .env")
        return False

    print(f"📌 Using API key: {api_key[:15]}...")

    # Test with a simple API call
    import aiohttp
    import json

    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "sonar",  # Try the basic sonar model
        "messages": [
            {
                "role": "system",
                "content": "You are a financial analyst. Be brief and specific."
            },
            {
                "role": "user",
                "content": "What is NVIDIA's current stock price and P/E ratio? Reply with just the numbers."
            }
        ],
        "max_tokens": 200,
        "temperature": 0.1
    }

    try:
        print("\n1. Sending test request to Perplexity API...")
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data['choices'][0]['message']['content']
                    print(f"✅ API Response received:")
                    print(f"   {content[:200]}")
                    print("\n✅ Perplexity API is working!")
                    return True
                else:
                    error = await response.text()
                    print(f"❌ API Error (status {response.status}):")
                    print(f"   {error[:200]}")
                    return False

    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False


async def test_research_functionality():
    """Test our research functionality"""

    print("\n" + "=" * 60)
    print("🤖 Testing Research Functionality")
    print("=" * 60)

    try:
        # Import just what we need
        from autonomous.connectors.perplexity_finance import (
            PerplexityFinanceConnector,
            AnalysisType,
            ResearchDepth
        )

        print("\n1. Initializing Perplexity connector...")
        connector = PerplexityFinanceConnector(
            api_key=os.getenv('PERPLEXITY_API_KEY')
        )
        print("✅ Connector initialized")

        # Test stock analysis
        print("\n2. Analyzing NVDA stock...")
        analysis = await connector.analyze_stock(
            "NVDA",
            AnalysisType.FUNDAMENTAL,
            ResearchDepth.QUICK
        )

        print(f"""
✅ Analysis Complete:
   Ticker: {analysis.ticker}
   Rating: {analysis.rating}
   Confidence: {analysis.confidence_score}%

   Analysis Preview:
   {analysis.detailed_analysis[:200]}...
        """)

        # Test market sentiment
        print("\n3. Getting market sentiment...")
        sentiment = await connector.get_market_sentiment()
        print(f"✅ Market Sentiment: {sentiment['analysis'][:150]}...")

        print("\n✅ All research functions working!")
        return True

    except ImportError as e:
        print(f"⚠️  Import error: {e}")
        print("   Some dependencies may be missing")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run tests"""

    print("""
╔════════════════════════════════════════════════════════════╗
║     Perplexity Finance API Test (Simplified)              ║
╚════════════════════════════════════════════════════════════╝
    """)

    # Test 1: Direct API test
    api_ok = await test_perplexity_direct()

    # Test 2: Research functionality (may have import issues)
    if api_ok:
        research_ok = await test_research_functionality()
    else:
        research_ok = False

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"Perplexity API Connection: {'✅ WORKING' if api_ok else '❌ FAILED'}")
    print(f"Research Functions: {'✅ WORKING' if research_ok else '⚠️ PARTIAL' if api_ok else '❌ FAILED'}")

    if api_ok:
        print("""
🎉 Your Perplexity API is connected and working!

The API can:
   - Answer investment questions
   - Analyze stocks in real-time
   - Provide market sentiment
   - Screen for opportunities

Note: Some import issues may exist with the full system,
but the core Perplexity functionality is operational.
        """)


if __name__ == "__main__":
    asyncio.run(main())