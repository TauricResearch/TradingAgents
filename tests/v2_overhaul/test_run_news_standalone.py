
import sys
import os
import json
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(str(Path(__file__).parent))

try:
    from tradingagents.agents.utils.agent_utils import get_news, get_global_news
    from tradingagents.utils.anonymizer import TickerAnonymizer
except ImportError:
    print("❌ Error: Could not import required modules.")
    sys.exit(1)

def run_news_standalone(ticker="PLTR"):
    print(f"🚀 STANDALONE NEWS ANALYST RUN: {ticker}")
    print("="*60)
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Anonymization
    print("🎭 Anonymizing Ticker...")
    anonymizer = TickerAnonymizer()
    anonymized_ticker = anonymizer.anonymize_ticker(ticker)
    print(f"   Real: {ticker} -> Anon: {anonymized_ticker}")
    
    # 2. Tool Execution (Real Network Calls)
    print("\n📡 Executing Tools (Real Network Calls)...")
    
    # A. Global News
    print("\n[TOOL] get_global_news:")
    try:
        global_news = get_global_news.invoke({
            "curr_date": current_date,
            "look_back_days": 3,
            "limit": 3
        })
        print(f"✅ Result Length: {len(global_news)}")
        print(f"Snippet: {str(global_news)[:200]}...")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # B. Company News
    print(f"\n[TOOL] get_news for {ticker}:")
    try:
        # Note: In the real agent, the LLM decides the query. We simulate a standard query.
        comp_news = get_news.invoke({
            "ticker": ticker,
            "query": f"{ticker} stock news",
            "start_date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
            "end_date": current_date
        })
        print(f"✅ Result Length: {len(comp_news)}")
        print(f"Snippet: {str(comp_news)[:200]}...")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # 3. Construct System Prompt
    print("\n📜 GENERATING SYSTEM PROMPT...")
    
    tool_names = "get_news, get_global_news"
    system_message = (
        "You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for company-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
        + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
    )
    
    full_prompt = (
        f"SYSTEM: You are a helpful AI assistant, collaborating with other assistants."
        f" Use the provided tools to progress towards answering the question."
        f" If you are unable to fully answer, that's OK; another assistant with different tools"
        f" will help where you left off. Execute what you can to make progress."
        f" If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
        f" prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
        f" You have access to the following tools: {tool_names}.\n{system_message}"
        f"For your reference, the current date is {current_date}. We are looking at the company {anonymized_ticker}"
    )
    
    print("-" * 60)
    print(full_prompt)
    print("-" * 60)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_news_standalone(sys.argv[1])
    else:
        run_news_standalone("PLTR")
