#!/usr/bin/env python3
"""
Integrated Langgraph Demo - All Agents Working Together
Shows how screening, pump detection, and analysis agents work in the unified graph.
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from tradingagents.graph.trading_graph import TradingAgentsGraph


def demo_integrated_agents():
    """
    Demonstrate all agents working together in the langgraph architecture.
    """
    
    print("\n" + "="*80)
    print("🤖 INTEGRATED AGENTIC ARCHITECTURE DEMO")
    print("="*80)
    print("\nArchitecture Overview:")
    print("  1. Screening Agent - Scans market for candidates")
    print("  2. Pump Detection Agent - Identifies pre-pump opportunities")
    print("  3. Market Analyst - Technical analysis")
    print("  4. News Analyst - News sentiment")
    print("  5. Social Analyst - Social media buzz")
    print("  6. Fundamentals Analyst - Company fundamentals")
    print("  7. Bull Researcher - Bullish perspective")
    print("  8. Bear Researcher - Bearish perspective")
    print("  9. Research Manager - Synthesizes debate")
    print("  10. Trader - Makes trading decision")
    print("  11. Risk Managers - Risk analysis")
    print("\n" + "="*80 + "\n")
    
    # Configuration
    selected_analysts = ["market", "social", "news", "fundamentals"]
    trade_date = datetime.now().strftime("%Y-%m-%d")
    ticker = "NVDA"
    
    print(f"Configuration:")
    print(f"  - Analysts: {', '.join(selected_analysts)}")
    print(f"  - Include Screening: Yes")
    print(f"  - Include Pump Detection: Yes")
    print(f"  - Trade Date: {trade_date}")
    print(f"  - Ticker: {ticker}")
    print("\n" + "="*80 + "\n")
    
    try:
        # Create graph with all agents enabled
        print("🚀 Initializing Integrated Trading Agents Graph...\n")
        
        graph = TradingAgentsGraph(
            selected_analysts=selected_analysts,
            debug=False,
            include_screening=True,  # Enable screening agent
            include_pump_detection=True,  # Enable pump detection agent
        )
        
        print("✅ Graph initialized successfully!\n")
        print("="*80)
        print("AGENT WORKFLOW SEQUENCE")
        print("="*80 + "\n")
        
        print("Step 1: SCREENING AGENT")
        print("  - Scans market for interesting candidates")
        print("  - Uses: get_market_movers, get_trending_social, get_earnings_calendar")
        print("  - Output: List of potential stocks to analyze\n")
        
        print("Step 2: PUMP DETECTION AGENT")
        print("  - Analyzes selected stock for pump signals")
        print("  - Uses: Volume spike, Price acceleration, Social sentiment, etc.")
        print("  - Output: Pump probability score (0-100)\n")
        
        print("Step 3: MARKET ANALYST")
        print("  - Technical analysis of the stock")
        print("  - Uses: RSI, MACD, Moving averages, Bollinger Bands")
        print("  - Output: Technical trend report\n")
        
        print("Step 4: SOCIAL MEDIA ANALYST")
        print("  - Analyzes social sentiment (Reddit, Twitter, etc.)")
        print("  - Uses: get_trending_social, sentiment analysis")
        print("  - Output: Social buzz and sentiment report\n")
        
        print("Step 5: NEWS ANALYST")
        print("  - Analyzes recent news and insider activity")
        print("  - Uses: get_news, get_insider_transactions, get_insider_sentiment")
        print("  - Output: News sentiment and insider activity report\n")
        
        print("Step 6: FUNDAMENTALS ANALYST")
        print("  - Analyzes company fundamentals")
        print("  - Uses: P/E ratio, Revenue growth, Financial statements")
        print("  - Output: Fundamental analysis report\n")
        
        print("Step 7: BULL RESEARCHER")
        print("  - Makes bullish case based on all analysis")
        print("  - Synthesizes positive signals")
        print("  - Output: Bullish investment thesis\n")
        
        print("Step 8: BEAR RESEARCHER")
        print("  - Makes bearish case based on all analysis")
        print("  - Synthesizes negative signals")
        print("  - Output: Bearish investment thesis\n")
        
        print("Step 9: RESEARCH MANAGER")
        print("  - Evaluates both bull and bear perspectives")
        print("  - Makes final investment decision")
        print("  - Output: FINAL INVESTMENT RECOMMENDATION\n")
        
        print("Step 10: TRADER")
        print("  - Creates trading plan (entry, stop, target)")
        print("  - Output: Trading execution plan\n")
        
        print("Step 11: RISK MANAGERS")
        print("  - Debate risk levels (Risky, Neutral, Safe)")
        print("  - Final risk assessment")
        print("  - Output: Risk-adjusted final decision\n")
        
        print("="*80 + "\n")
        
        # Run analysis
        print("⏳ Running full analysis through all agents...\n")
        
        init_state = {
            "trade_date": trade_date,
            "company_of_interest": ticker,
            "messages": [],
        }
        
        # Note: The actual execution would happen here, but we're showing the architecture
        # In real usage: final_state, signal = graph.propagate(ticker, trade_date)
        
        print("✅ Analysis would complete with:\n")
        print("  - Pump detection score for pre-entry opportunities")
        print("  - Technical analysis with entry/exit points")
        print("  - Social and news sentiment context")
        print("  - Fundamental health assessment")
        print("  - Integrated investment recommendation")
        print("  - Risk-adjusted position sizing")
        
        print("\n" + "="*80)
        print("KEY FEATURES OF INTEGRATED ARCHITECTURE")
        print("="*80 + "\n")
        
        print("✅ Multi-Agent Collaboration:")
        print("   - Agents share state and findings")
        print("   - Each agent builds on previous analysis")
        print("   - Final decision combines all perspectives\n")
        
        print("✅ Specialized Expertise:")
        print("   - Screening agent finds opportunities")
        print("   - Pump detection agent spots momentum")
        print("   - Fundamental analysts verify quality")
        print("   - Technical analysts confirm entry points")
        print("   - Risk managers ensure protection\n")
        
        print("✅ Debate & Consensus:")
        print("   - Bull vs Bear research debate")
        print("   - Risk vs Reward discussion")
        print("   - Final consensus decision\n")
        
        print("✅ Flexible Configuration:")
        print("   - Enable/disable agents as needed")
        print("   - Choose specific analysts")
        print("   - Customize workflow")
        print("   - Adjust risk profiles\n")
        
        print("✅ Unified Tool Access:")
        print("   - All agents access same tools")
        print("   - Consistent data retrieval")
        print("   - Shared analysis results\n")
        
        print("="*80)
        print("USAGE EXAMPLE")
        print("="*80 + "\n")
        
        print("Python Code:")
        print("""
from tradingagents.graph.trading_graph import TradingAgentsGraph

# Create graph with screening and pump detection
graph = TradingAgentsGraph(
    selected_analysts=["market", "social", "news", "fundamentals"],
    include_screening=True,
    include_pump_detection=True,
)

# Run analysis
ticker = "NVDA"
trade_date = "2025-12-05"
final_state, signal = graph.propagate(ticker, trade_date)

# Access results from all agents
pump_report = final_state.get("pump_report")
screening_report = final_state.get("screening_report")
market_report = final_state.get("market_report")
final_decision = final_state.get("final_trade_decision")
        """)
        
        print("\n" + "="*80)
        print("NEXT STEPS")
        print("="*80 + "\n")
        
        print("1. Run screening to find candidates:")
        print("   graph = TradingAgentsGraph(include_screening=True)")
        print("")
        print("2. Detect pump opportunities:")
        print("   graph = TradingAgentsGraph(include_pump_detection=True)")
        print("")
        print("3. Full integrated analysis:")
        print("   graph = TradingAgentsGraph(")
        print("       include_screening=True,")
        print("       include_pump_detection=True)")
        print("")
        print("4. Then run: final_state, signal = graph.propagate(ticker, date)")
        
        print("\n" + "="*80 + "\n")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = demo_integrated_agents()
    sys.exit(0 if success else 1)
