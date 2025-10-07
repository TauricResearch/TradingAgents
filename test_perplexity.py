#!/usr/bin/env python
"""
Quick test script to verify Perplexity API connectivity and functionality.
"""

import asyncio
import os
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv()

# Add current directory to path
sys.path.append('.')

from autonomous.connectors.perplexity_finance import (
    PerplexityFinanceConnector,
    AnalysisType,
    ResearchDepth
)


async def test_perplexity():
    """Test Perplexity API functionality"""

    print("=" * 60)
    print("🔍 Testing Perplexity Finance API")
    print("=" * 60)

    try:
        # Initialize connector
        print("\n1. Initializing Perplexity connector...")
        connector = PerplexityFinanceConnector(
            api_key=os.getenv('PERPLEXITY_API_KEY')
        )
        print("✅ Connector initialized")

        # Test 1: Analyze a single stock
        print("\n2. Testing stock analysis (NVDA)...")
        analysis = await connector.analyze_stock(
            "NVDA",
            AnalysisType.FUNDAMENTAL,
            ResearchDepth.QUICK
        )

        print(f"""
✅ Stock Analysis Complete:
   - Ticker: {analysis.ticker}
   - Current Price: ${analysis.current_price:.2f if analysis.current_price else 'N/A'}
   - Fair Value: ${analysis.fair_value:.2f if analysis.fair_value else 'N/A'}
   - P/E Ratio: {analysis.pe_ratio if analysis.pe_ratio else 'N/A'}
   - Rating: {analysis.rating}
   - Confidence: {analysis.confidence_score}%

   Analysis Preview:
   {analysis.detailed_analysis[:300]}...
        """)

        # Test 2: Market sentiment
        print("\n3. Testing market sentiment analysis...")
        sentiment = await connector.get_market_sentiment()

        print(f"""
✅ Market Sentiment:
   {sentiment['analysis'][:300]}...
        """)

        # Test 3: Stock screening
        print("\n4. Testing stock screening...")
        query = "Find undervalued technology stocks with P/E under 25"
        results = await connector.screen_stocks(query, max_results=5)

        print(f"""
✅ Screening Results for: "{query}"
   Found {results.total_results} stocks

   Top Results:""")

        for stock in results.stocks[:3]:
            print(f"   - {stock.get('ticker', 'N/A')}: ${stock.get('price', 0):.2f}")

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED - Perplexity API is working!")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_research_agent():
    """Test the AI Research Agent with Perplexity"""

    print("\n" + "=" * 60)
    print("🤖 Testing AI Research Agent")
    print("=" * 60)

    try:
        from autonomous.research.ai_research_agent import (
            AIResearchAgent,
            ResearchQuery,
            ResearchMode
        )

        # Initialize agent
        print("\n1. Initializing AI Research Agent...")
        agent = AIResearchAgent(
            openai_api_key=os.getenv('OPENAI_API_KEY'),
            perplexity_connector=PerplexityFinanceConnector(
                api_key=os.getenv('PERPLEXITY_API_KEY')
            )
        )
        print("✅ Agent initialized")

        # Test natural language query
        print("\n2. Testing natural language query...")
        question = "What are the top 3 undervalued stocks in the technology sector right now?"
        print(f"Question: {question}")

        answer = await agent.answer_question(question)

        print(f"""
✅ Answer received:
{answer[:500]}...
        """)

        print("\n" + "=" * 60)
        print("✅ AI Research Agent is working!")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""

    print("""
╔════════════════════════════════════════════════════════════╗
║        Perplexity Finance API Integration Test            ║
╚════════════════════════════════════════════════════════════╝
    """)

    # Check for API key
    if not os.getenv('PERPLEXITY_API_KEY'):
        print("❌ PERPLEXITY_API_KEY not found in .env file")
        return

    print(f"📌 Using Perplexity API key: {os.getenv('PERPLEXITY_API_KEY')[:10]}...")

    # Run tests
    perplexity_ok = await test_perplexity()

    if perplexity_ok and os.getenv('OPENAI_API_KEY'):
        agent_ok = await test_research_agent()
    else:
        print("\n⚠️  Skipping AI Research Agent test (requires OpenAI API key)")
        agent_ok = False

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"Perplexity API: {'✅ PASSED' if perplexity_ok else '❌ FAILED'}")
    print(f"Research Agent: {'✅ PASSED' if agent_ok else '⏭️  SKIPPED' if not os.getenv('OPENAI_API_KEY') else '❌ FAILED'}")

    if perplexity_ok:
        print("""
🎉 SUCCESS! Your AI research system is ready to:
   - Analyze stocks with real-time data
   - Answer complex investment questions
   - Screen for opportunities
   - Monitor market sentiment

Next steps:
   1. Run the interactive CLI: python autonomous/research/research_cli.py
   2. Run the full demo: python research_demo.py
   3. Start the autonomous system: python autonomous_trader.py
        """)


if __name__ == "__main__":
    asyncio.run(main())