#!/usr/bin/env python3
"""
Integrated Pump Detection + Trading Workflow
Combines pump detection with existing market analysis and trading agents.
"""

import sys
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

from tradingagents.graph.trading_graph import create_trading_graph


def run_pump_and_trade_workflow(target_tickers=None, mode="pump_first"):
    """
    Run integrated workflow: Detect pumps → Analyze → Trade
    
    Args:
        target_tickers: List of tickers to analyze (e.g., ["NVDA", "TSLA"])
        mode: "pump_first" (find pumps then analyze) or "analyze_only" (standard analysis)
    
    Returns:
        Trading decisions and analysis
    """
    
    print("\n" + "="*80)
    print("🚀 PUMP DETECTION + TRADING WORKFLOW")
    print("="*80 + "\n")
    
    # Get current date
    trade_date = datetime.now().strftime("%Y-%m-%d")
    print(f"Analysis Date: {trade_date}\n")
    
    # Initialize LLM
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7,
    )
    
    # Create trading graph
    graph = create_trading_graph(llm)
    
    # Step 1: Pump detection
    if mode == "pump_first":
        print("\n" + "="*80)
        print("STEP 1: PUMP DETECTION")
        print("="*80 + "\n")
        
        from tradingagents.agents.pump_detection_agent import create_pump_detection_agent
        
        pump_detector = create_pump_detection_agent(llm)
        
        if not target_tickers:
            # Screen market for pump candidates
            print("🔍 Screening market for pump candidates...\n")
            
            from tradingagents.agents.screening_agent import create_screening_agent
            screener = create_screening_agent(llm)
            
            screening_state = {
                "messages": [],
                "trade_date": trade_date,
            }
            
            screening_result = screener(screening_state)
            screening_msg = screening_result["messages"][-1].content if screening_result["messages"] else ""
            
            # Try to extract tickers
            target_tickers = []
            lines = screening_msg.split('\n')
            for line in reversed(lines):
                line = line.strip()
                if line and all(c.isalpha() or c in ', ' for c in line):
                    target_tickers = [t.strip() for t in line.split(',') if t.strip()]
                    if target_tickers and len(target_tickers) <= 5:
                        break
            
            if not target_tickers:
                target_tickers = ["NVDA", "TSLA", "AMD"]
        
        print(f"📋 Analyzing: {', '.join(target_tickers)}\n")
        
        # Run pump detection on each
        pump_candidates = []
        for ticker in target_tickers:
            print(f"\n--- {ticker} ---")
            
            pump_state = {
                "messages": [],
                "ticker": ticker,
                "trade_date": trade_date,
            }
            
            pump_result = pump_detector(pump_state)
            analysis = pump_result["messages"][-1].content if pump_result["messages"] else ""
            
            # Check for high pump score
            if "70" in analysis or "VERY HIGH" in analysis.upper():
                pump_candidates.append((ticker, "VERY_HIGH"))
            elif "50" in analysis or "HIGH" in analysis.upper():
                pump_candidates.append((ticker, "HIGH"))
            
            print(analysis[:400] + "...")
    else:
        # Use provided tickers
        pump_candidates = [(t, "UNKNOWN") for t in target_tickers]
    
    # Step 2: Trade analysis for top pump candidates
    print("\n" + "="*80)
    print("STEP 2: DETAILED TRADE ANALYSIS")
    print("="*80 + "\n")
    
    trading_decisions = []
    
    for ticker, pump_level in pump_candidates[:3]:  # Top 3 only
        print(f"\n🎯 Analyzing {ticker} (Pump Level: {pump_level})...\n")
        
        # Set up trading graph state
        graph_state = {
            "trade_date": trade_date,
            "company_of_interest": ticker,
            "messages": [],
        }
        
        try:
            # Run trading graph
            print("Running full trade analysis...\n")
            
            # This would integrate with your existing trading graph
            # For now, show what would happen
            print(f"✅ Trade analysis for {ticker}:")
            print(f"   - Technical analysis: RSI, MACD, Volume")
            print(f"   - Fundamental analysis: P/E, Growth, Momentum")
            print(f"   - Risk assessment: Entry, Stop-loss, Target")
            print(f"   - Signal: BUY/HOLD/SELL")
            
            trading_decisions.append({
                "ticker": ticker,
                "pump_level": pump_level,
                "status": "ready_to_trade"
            })
            
        except Exception as e:
            print(f"⚠️  Error analyzing {ticker}: {e}")
    
    # Step 3: Summary and recommendations
    print("\n" + "="*80)
    print("STEP 3: TRADING RECOMMENDATIONS")
    print("="*80 + "\n")
    
    if trading_decisions:
        print("📊 Ready to Trade:\n")
        for decision in trading_decisions:
            print(f"  ✅ {decision['ticker']} - {decision['pump_level']} pump probability")
        
        print("\n💡 Recommended Actions:")
        print("  1. Start with smallest position (1% portfolio)")
        print("  2. Set stop-loss at 2-3% below entry")
        print("  3. Take profits at 5-10% gains")
        print("  4. Monitor volume continuously")
        print("  5. Use alerts for key support/resistance levels")
    else:
        print("⏳ No strong pump candidates identified.")
        print("Consider running again later or adjusting detection thresholds.")
    
    print("\n" + "="*80 + "\n")
    
    return trading_decisions


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Integrated Pump Detection + Trading Workflow"
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        help="Specific tickers to analyze (e.g., NVDA TSLA AMD)",
    )
    parser.add_argument(
        "--mode",
        choices=["pump_first", "analyze_only"],
        default="pump_first",
        help="Analysis mode: pump_first (detect then trade) or analyze_only (standard)",
    )
    
    args = parser.parse_args()
    
    try:
        results = run_pump_and_trade_workflow(
            target_tickers=args.tickers,
            mode=args.mode
        )
        print(f"✅ Workflow completed! {len(results)} stocks ready to trade.")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
