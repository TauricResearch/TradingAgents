
import sys
import os
import json
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(str(Path(__file__).parent))

try:
    from tradingagents.agents.utils.agent_utils import get_news
    from tradingagents.utils.anonymizer import TickerAnonymizer
except ImportError:
    print("❌ Error: Could not import required modules.")
    sys.exit(1)

def run_social_standalone(ticker="PLTR"):
    print(f"🚀 STANDALONE SOCIAL ANALYST RUN: {ticker}")
    print("="*60)
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Anonymization
    print("🎭 Anonymizing Ticker...")
    anonymizer = TickerAnonymizer()
    anonymized_ticker = anonymizer.anonymize_ticker(ticker)
    print(f"   Real: {ticker} -> Anon: {anonymized_ticker}")
    
    # 2. Tool Execution (Real Network Calls)
    print("\n📡 Executing Tools (Real Network Calls)...")
    
    print(f"\n[TOOL] get_news for {ticker} (Sentiment Query):")
    try:
        # Simulating a social sentiment query the LLM might generate
        comp_news = get_news.invoke({
            "ticker": ticker,
            "query": f"{ticker} social media sentiment and opinion",
            "start_date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
            "end_date": current_date
        })
        print(f"✅ Result Length: {len(comp_news)}")
        print(f"Snippet: {str(comp_news)[:200]}...")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # 3. Construct System Prompt
    print("\n📜 GENERATING SYSTEM PROMPT...")
    
    tool_names = "get_news"
    
    system_message = (
        "You are a social media and company specific news researcher/analyst tasked with analyzing social media posts, recent company news, and public sentiment for a specific company over the past week. You will be given a company's name your objective is to write a comprehensive long report detailing your analysis, insights, and implications for traders and investors on this company's current state after looking at social media and what people are saying about that company, analyzing sentiment data of what people feel each day about the company, and looking at recent company news. Use the get_news(query, start_date, end_date) tool to search for company-specific news and social media discussions. Try to look at all sources possible from social media to sentiment to news. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."
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
        f"For your reference, the current date is {current_date}. The current company we want to analyze is {anonymized_ticker}"
    )
    
    print("-" * 60)
    print(full_prompt)
    print("-" * 60)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_social_standalone(sys.argv[1])
    else:
        run_social_standalone("PLTR")
