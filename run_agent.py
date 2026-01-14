import sys
import os
import argparse
from dotenv import load_dotenv
from datetime import datetime
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

def main():
    parser = argparse.ArgumentParser(description="Run Trading Agent with Deep Analysis and Claude Sonnet 4.5 Thinking")
    parser.add_argument("ticker", type=str, help="Stock Ticker Symbol (e.g., AAPL)")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y-%m-%d"), help="Trade Date (YYYY-MM-DD)")
    
    args = parser.parse_args()

    # Load environment variables
    load_dotenv()
    
    # 1. Configuration Setup
    # Mixing CLI args with required distinct configuration
    config = DEFAULT_CONFIG.copy()
    
    # User Request: "anthropic claude sonnet 4.5 thinking"
    config["llm_provider"] = "anthropic"
    config["deep_think_llm"] = "claude-sonnet-4-5-thinking"
    
    # FIX: Clear backend_url so it doesn't default to OpenAI's endpoint, 
    # unless specified in environment (e.g. for proxy)
    config["backend_url"] = os.getenv("BACKEND_URL")
    
    # Also setting quick_think to a high-quality model to support the deep analysis, 
    # though usually this is lighter. User emphasis was on "thinking" model.
    config["quick_think_llm"] = "claude-sonnet-4-5-thinking" 
    
    # User Request: "Deep Analysis"
    # We enable debate rounds to trigger the deep thinking loops
    config["max_debate_rounds"] = 2
    config["max_risk_discuss_rounds"] = 2
    
    # 2. Tool Configuration (Data Vendors)
    # FIX: Use Google for news to avoid AlphaVantage rate limits (and handle fallback better)
    config["tool_vendors"] = {
        "get_news": "google",
        "get_global_news": "google"
    }
    
    print(f"🚀 Initializing Trading Agent for {args.ticker} on {args.date}")
    print(f"🧠 Model: {config['deep_think_llm']} (Provider: {config['llm_provider']})")
    print(f"🔍 Deep Analysis: ENABLED (Debate Rounds: {config['max_debate_rounds']})")
    print(f"📰 News Vendor: Google (Rate Limit Bypass)")
    
    # 3. Initialize Graph
    # User Request: "Fundamental Analysis" (Explicitly included)
    analysts = ["market", "fundamentals", "news", "social"]
    
    try:
        agent_graph = TradingAgentsGraph(
            selected_analysts=analysts,
            config=config,
            debug=True # Enable debug to see the "Thinking" process in logs
        )
        
        # 4. Run Propagation
        final_state, signal = agent_graph.propagate(args.ticker, args.date)
        
        # 5. Output Summary
        print("\n" + "="*50)
        print(f"🏁 FINAL DECISION for {args.ticker}")
        print("="*50)
        
        decision = final_state.get("final_trade_decision", "NO DECISION")
        if isinstance(decision, dict):
            print(f"ACTION: {decision.get('action')}")
            print(f"QUANTITY: {decision.get('quantity')}")
            print(f"REASONING: {decision.get('reasoning')}")
        else:
            print(f"DECISION: {decision}")
            
        print("\n✅ Run Complete. Check 'eval_results' for detailed logs and reports.")
        
        # 6. Generate HTML Report
        print("\n📊 Generating Standalone HTML Report...")
        
        # 6.1 Identify Reports Directory
        base_dir = os.path.dirname(os.path.abspath(__file__))
        results_dir = os.path.join(base_dir, "results", args.ticker, args.date)
        reports_dir = os.path.join(results_dir, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        
        # 6.2 Write Markdown Files from State
        # Map state keys to friendly filenames
        report_map = {
            "market_report": "market_analyst.md",
            "news_report": "news_analyst.md",
            "fundamentals_report": "fundamentals_analyst.md",
            "sentiment_report": "sentiment_analyst.md",
            "investment_plan": "investment_plan.md",
            "trader_investment_plan": "trader_decision.md" # Optional/Internal
        }
        
        
        print(f"DEBUG: Calculated raw reports_dir: {reports_dir}")
        if not os.path.exists(reports_dir):
             print(f"DEBUG: creating directory {reports_dir}")
             os.makedirs(reports_dir, exist_ok=True)

        for key, filename in report_map.items():
            content = final_state.get(key)
            if content:
                # Ensure directory exists (User Request)
                if not os.path.exists(reports_dir):
                    os.makedirs(reports_dir, exist_ok=True)
                    
                file_path = os.path.join(reports_dir, filename)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(str(content))
        
        # 6.3 Call Generator with CORRECT Path
        import subprocess
        generator_script = os.path.join(base_dir, "scripts", "generate_report_html.py")
        
        try:
            # generator expects: <report_dir>
            print(f"DEBUG: Calling generator with path: {reports_dir}")
            cmd = [sys.executable, generator_script, reports_dir]
            subprocess.run(cmd, check=True)
            print(f"✅ Report Generated Successfully: {reports_dir}/index.html")
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Report Generation Failed: {e}")
        except Exception as e:
            print(f"⚠️ Error running report generator: {e}")
        
        
    except Exception as e:
        print(f"\n❌ ERROR: Agents failed to run: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
