#!/usr/bin/env python3
"""
Pump Detection Screening Tool
Identifies stocks likely to pump before they happen.
Usage: python pump_screening.py [--ticker SYMBOL] [--date YYYY-mm-dd]
"""

import sys
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

from tradingagents.agents.pump_detection_agent import create_pump_detection_agent
from tradingagents.agents.screening_agent import create_screening_agent


def run_pump_detection(ticker=None, date=None):
    """
    Run pump detection analysis on one or more stocks.
    
    Args:
        ticker: Optional specific ticker to analyze (e.g., "NVDA")
        date: Optional analysis date (default: today)
    """
    
    # Initialize LLM
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7,
    )
    
    # Create agents
    pump_detector = create_pump_detection_agent(llm)
    screener = create_screening_agent(llm)
    
    print("\n" + "="*80)
    print("🚀 PUMP DETECTION SCREENING SYSTEM")
    print("="*80 + "\n")
    
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    print(f"Analysis Date: {date}")
    print("-" * 80)
    
    # Step 1: Screen the market if no specific ticker provided
    if ticker is None:
        print("\n📊 STEP 1: Screening Market for Pump Candidates...\n")
        
        screening_state = {
            "messages": [],
            "trade_date": date,
        }
        
        # Run screening agent
        screening_result = screener(screening_state)
        
        # Extract recommended tickers from screening result
        screening_message = screening_result["messages"][-1].content if screening_result["messages"] else ""
        print("Screening Agent Output:")
        print(screening_message)
        
        # Try to extract tickers
        tickers = []
        lines = screening_message.split('\n')
        for line in reversed(lines):
            line = line.strip()
            if line and all(c.isalpha() or c in ', ' for c in line):
                # This looks like a ticker list
                tickers = [t.strip() for t in line.split(',') if t.strip()]
                if tickers and len(tickers) <= 5:
                    break
        
        if not tickers:
            print("\n⚠️  No tickers identified by screening agent. Using market movers instead...")
            tickers = ["NVDA", "TSLA", "AAPL", "AMD", "MSTR"]
    else:
        tickers = [ticker.upper()]
    
    print(f"\n📋 Tickers to Analyze: {', '.join(tickers)}\n")
    
    # Step 2: Run pump detection on each ticker
    print("\n" + "="*80)
    print("🔍 STEP 2: Running Pump Detection Analysis...")
    print("="*80 + "\n")
    
    all_analyses = []
    
    for tick in tickers:
        print(f"\n--- Analyzing {tick} ---\n")
        
        pump_state = {
            "messages": [],
            "ticker": tick,
            "trade_date": date,
        }
        
        # Run pump detection agent
        pump_result = pump_detector(pump_state)
        
        analysis_output = pump_result["messages"][-1].content if pump_result["messages"] else ""
        print(analysis_output)
        
        all_analyses.append({
            "ticker": tick,
            "analysis": analysis_output,
        })
        
        print("-" * 80)
    
    # Step 3: Summary
    print("\n" + "="*80)
    print("📈 PUMP DETECTION SUMMARY")
    print("="*80 + "\n")
    
    print("Analyzed Tickers:")
    for item in all_analyses:
        print(f"  • {item['ticker']}")
    
    print("\n💡 Next Steps:")
    print("  1. Review stocks with pump score > 50")
    print("  2. Set up alerts for volume/price confirmation")
    print("  3. Use tight stop-losses for pump trades")
    print("  4. Scale in gradually as pump develops")
    print("  5. Exit on volume decline or resistance breakfailure")
    
    print("\n⚠️  Risk Warnings:")
    print("  • Pump trades are high-risk, short-term plays")
    print("  • Position sizing: Max 1-2% of portfolio per trade")
    print("  • Stop-loss must be set at entry (2-3% below)")
    print("  • Not suitable for long-term holdings")
    print("  • Monitor continuously; don't leave unattended")
    
    print("\n" + "="*80 + "\n")
    
    return all_analyses


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pump Detection Screening Tool - Identify pre-pump stocks"
    )
    parser.add_argument(
        "--ticker",
        type=str,
        help="Specific ticker to analyze (e.g., NVDA)",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Analysis date (YYYY-mm-dd), default is today",
    )
    
    args = parser.parse_args()
    
    try:
        results = run_pump_detection(ticker=args.ticker, date=args.date)
        print("✅ Pump detection analysis completed successfully!")
    except Exception as e:
        print(f"❌ Error during pump detection: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
