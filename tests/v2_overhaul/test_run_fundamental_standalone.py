
import sys
import os
import json
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(str(Path(__file__).parent))

try:
    from tradingagents.agents.utils.agent_utils import get_fundamentals
    from tradingagents.utils.anonymizer import TickerAnonymizer
except ImportError:
    print("❌ Error: Could not import required modules.")
    sys.exit(1)

def run_fundamental_standalone(ticker="PLTR"):
    print(f"🚀 STANDALONE FUNDAMENTAL ANALYST RUN: {ticker}")
    print("="*60)
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Anonymization
    print("🎭 Anonymizing Ticker...")
    anonymizer = TickerAnonymizer()
    anonymized_ticker = anonymizer.anonymize_ticker(ticker)
    print(f"   Real: {ticker} -> Anon: {anonymized_ticker}")
    
    # 2. Tool Execution (Real Network Calls)
    print("\n📡 Executing Tools (Real Network Calls)...")
    
    print(f"\n[TOOL] get_fundamentals for {ticker}:")
    try:
        comp_fund = get_fundamentals.invoke({
            "ticker": ticker,
            "curr_date": current_date
        })
        print(f"✅ Result Length: {len(str(comp_fund))}")
        print(f"Snippet: {str(comp_fund)[:500]}...")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # 3. Construct System Prompt
    print("\n📜 GENERATING SYSTEM PROMPT...")
    
    tool_names = "get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement"
    
    system_message = (
        "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
        + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
        + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
    )
    
    full_prompt = (
        f"SYSTEM: You are a helpful AI assistant, collaborating with other assistants."
        f" Use the provided tools to progress towards answering the question."
        f" If you are unable to fully answer, that's OK; another assistant with different tools"
        f" will help where you left off. Execute what you can to make progress."
        f" If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
        f" prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
        f" You have access to the following tools: {tool_names}.\n{system_message}"
        f"For your reference, the current date is {current_date}. The company we want to look at is {anonymized_ticker}"
    )
    
    print("-" * 60)
    print(full_prompt)
    print("-" * 60)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_fundamental_standalone(sys.argv[1])
    else:
        run_fundamental_standalone("PLTR")
