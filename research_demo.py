#!/usr/bin/env python
"""
Research Demo - Example usage of the AI Research Agent
Demonstrates how to use natural language queries to analyze stocks and markets.
"""

import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

# Import our research components
from autonomous.research.ai_research_agent import (
    AIResearchAgent,
    ResearchQuery,
    ResearchMode,
    ScreeningCriteria
)
from autonomous.connectors.perplexity_finance import (
    PerplexityFinanceConnector,
    AnalysisType,
    ResearchDepth
)
from autonomous.core.cache import RedisCache


async def demo_stock_analysis():
    """Demo: Analyze individual stocks"""
    print("\n" + "="*60)
    print("DEMO 1: Individual Stock Analysis")
    print("="*60)

    # Initialize Perplexity connector
    perplexity = PerplexityFinanceConnector(
        api_key=os.getenv('PERPLEXITY_API_KEY')
    )

    # Analyze NVDA
    print("\n📊 Analyzing NVIDIA (NVDA)...")
    analysis = await perplexity.analyze_stock(
        "NVDA",
        AnalysisType.FUNDAMENTAL,
        ResearchDepth.STANDARD
    )

    print(f"""
    Current Price: ${analysis.current_price}
    Fair Value: ${analysis.fair_value}
    Upside Potential: {analysis.upside_potential}%
    P/E Ratio: {analysis.pe_ratio}
    Rating: {analysis.rating}
    Confidence: {analysis.confidence_score}%

    Bull Case: {analysis.bull_case[:200]}...
    Bear Case: {analysis.bear_case[:200]}...

    Key Risks:
    """ + '\n    '.join(f"- {risk}" for risk in analysis.key_risks[:3]))


async def demo_natural_language_research():
    """Demo: Natural language investment research"""
    print("\n" + "="*60)
    print("DEMO 2: Natural Language Investment Research")
    print("="*60)

    # Initialize AI Research Agent
    agent = AIResearchAgent(
        openai_api_key=os.getenv('OPENAI_API_KEY'),
        perplexity_connector=PerplexityFinanceConnector(
            api_key=os.getenv('PERPLEXITY_API_KEY')
        )
    )

    # Example questions
    questions = [
        "What are the most undervalued tech stocks right now?",
        "Should I invest in AI stocks or wait for a pullback?",
        "Compare Microsoft vs Apple as long-term investments",
        "What sectors look most promising for 2024?"
    ]

    # Process first question as example
    question = questions[0]
    print(f"\n❓ Question: {question}")
    print("\n🤖 Researching...")

    query = ResearchQuery(
        question=question,
        depth="standard",
        include_portfolio=False
    )

    response = await agent.research(query, mode=ResearchMode.COMPREHENSIVE)

    print(f"\n📝 Answer:\n{response.answer[:500]}...")

    if response.recommendations:
        print("\n💡 Top Recommendations:")
        for rec in response.recommendations[:3]:
            print(f"  • {rec}")

    if response.risks:
        print("\n⚠️  Key Risks:")
        for risk in response.risks[:3]:
            print(f"  • {risk}")

    print(f"\n📊 Confidence: {response.confidence:.0%}")


async def demo_stock_screening():
    """Demo: Screen for investment opportunities"""
    print("\n" + "="*60)
    print("DEMO 3: Stock Screening")
    print("="*60)

    # Initialize Perplexity connector
    perplexity = PerplexityFinanceConnector(
        api_key=os.getenv('PERPLEXITY_API_KEY')
    )

    # Screen for undervalued dividend stocks
    query = "Find undervalued dividend stocks with yields above 3% and stable earnings"
    print(f"\n🔍 Screening: {query}")

    filters = {
        "min_dividend_yield": 3.0,
        "max_pe": 20,
        "min_market_cap": 10  # $10B minimum
    }

    result = await perplexity.screen_stocks(query, max_results=10, filters=filters)

    print(f"\n📊 Found {result.total_results} stocks matching criteria:")
    print("\nTop 5 Results:")
    print("-" * 40)

    for stock in result.stocks[:5]:
        print(f"""
    Ticker: {stock.get('ticker', 'N/A')}
    Company: {stock.get('company_name', 'N/A')}
    Price: ${stock.get('price', 'N/A')}
    P/E: {stock.get('pe_ratio', 'N/A')}
    Market Cap: ${stock.get('market_cap', 'N/A')}B
    """ + "-" * 40)


async def demo_portfolio_opportunities():
    """Demo: Find opportunities based on portfolio"""
    print("\n" + "="*60)
    print("DEMO 4: Investment Opportunities")
    print("="*60)

    # Initialize AI Research Agent
    agent = AIResearchAgent(
        openai_api_key=os.getenv('OPENAI_API_KEY'),
        perplexity_connector=PerplexityFinanceConnector(
            api_key=os.getenv('PERPLEXITY_API_KEY')
        )
    )

    # Find opportunities for $50k investment
    print("\n💰 Finding opportunities for $50,000 investment...")
    print("   Risk: Medium | Horizon: Long-term")

    opportunities = await agent.find_opportunities(
        investment_amount=50000,
        risk_tolerance="medium",
        time_horizon="long"
    )

    print("\n📊 Investment Plan:")
    print(f"   Market Sentiment: {opportunities['market_conditions'].get('sentiment', 'N/A')}")

    if opportunities['allocation_strategy']:
        print("\n💼 Recommended Allocation:")
        total = 50000
        for ticker, amount in opportunities['allocation_strategy'].items():
            pct = (amount / total) * 100
            print(f"   • {ticker}: ${amount:,.0f} ({pct:.0f}%)")

    if opportunities['expected_returns']:
        returns = opportunities['expected_returns']
        print("\n📈 Expected Returns:")
        print(f"   • Expected: {returns['expected']:.1f}%")
        print(f"   • Best Case: {returns['best_case']:.1f}%")
        print(f"   • Worst Case: {returns['worst_case']:.1f}%")


async def demo_market_sentiment():
    """Demo: Analyze current market sentiment"""
    print("\n" + "="*60)
    print("DEMO 5: Market Sentiment Analysis")
    print("="*60)

    # Initialize Perplexity connector
    perplexity = PerplexityFinanceConnector(
        api_key=os.getenv('PERPLEXITY_API_KEY')
    )

    # Get overall market sentiment
    print("\n🌍 Analyzing overall market sentiment...")
    sentiment = await perplexity.get_market_sentiment()

    print(f"\nMarket Analysis:")
    print(sentiment['analysis'][:800])

    # Get tech sector sentiment
    print("\n💻 Analyzing technology sector...")
    tech_sentiment = await perplexity.get_market_sentiment("technology")

    print(f"\nTechnology Sector Analysis:")
    print(tech_sentiment['analysis'][:500])


async def demo_earnings_analysis():
    """Demo: Analyze recent earnings"""
    print("\n" + "="*60)
    print("DEMO 6: Earnings Analysis")
    print("="*60)

    # Initialize Perplexity connector
    perplexity = PerplexityFinanceConnector(
        api_key=os.getenv('PERPLEXITY_API_KEY')
    )

    # Analyze Apple's earnings
    print("\n📊 Analyzing Apple (AAPL) earnings...")
    earnings = await perplexity.analyze_earnings("AAPL", include_guidance=True)

    print(f"\nEarnings Analysis:")
    print(earnings['analysis'][:800])


async def demo_congressional_trades():
    """Demo: Find what Congress is trading"""
    print("\n" + "="*60)
    print("DEMO 7: Congressional Trading Activity")
    print("="*60)

    # Initialize AI Research Agent
    agent = AIResearchAgent(
        openai_api_key=os.getenv('OPENAI_API_KEY'),
        perplexity_connector=PerplexityFinanceConnector(
            api_key=os.getenv('PERPLEXITY_API_KEY')
        )
    )

    question = "What stocks have Congress members been buying recently and why might they be interested?"
    print(f"\n❓ Question: {question}")
    print("\n🤖 Researching congressional trades...")

    answer = await agent.answer_question(question)
    print(f"\n📝 Answer:\n{answer[:800]}...")


async def main():
    """Run all demos"""
    print("""
    ╔════════════════════════════════════════════════╗
    ║   AI-Powered Investment Research Demo         ║
    ║   Powered by Perplexity Finance & OpenAI      ║
    ╚════════════════════════════════════════════════╝
    """)

    # Check for required API keys
    if not os.getenv('PERPLEXITY_API_KEY'):
        print("❌ Error: PERPLEXITY_API_KEY not set in .env file")
        print("   Get your API key from: https://www.perplexity.ai/settings/api")
        return

    if not os.getenv('OPENAI_API_KEY'):
        print("❌ Error: OPENAI_API_KEY not set in .env file")
        return

    # Run demos
    try:
        # Individual analysis
        await demo_stock_analysis()

        # Natural language Q&A
        await demo_natural_language_research()

        # Stock screening
        await demo_stock_screening()

        # Portfolio opportunities
        await demo_portfolio_opportunities()

        # Market sentiment
        await demo_market_sentiment()

        # Earnings analysis
        await demo_earnings_analysis()

        # Congressional trades
        await demo_congressional_trades()

        print("\n" + "="*60)
        print("✅ All demos completed successfully!")
        print("="*60)

        print("""
    🚀 Next Steps:
    1. Run the interactive CLI: python autonomous/research/research_cli.py
    2. Integrate with your trading system
    3. Customize screening criteria for your strategy
    4. Add more data sources as needed
        """)

    except Exception as e:
        print(f"\n❌ Error running demos: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())