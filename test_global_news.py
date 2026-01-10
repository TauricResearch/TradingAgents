
from tradingagents.dataflows.alpha_vantage_news import get_global_market_news
from datetime import datetime, timedelta
import os

# Ensure env vars are loaded (assuming they are set in the shell running this)
if not os.getenv("ALPHA_VANTAGE_API_KEY"):
    print("WARNING: ALPHA_VANTAGE_API_KEY not set")

try:
    print("Testing get_global_market_news...")
    curr_date = datetime.now().strftime("%Y-%m-%d")
    print(f"Current Date: {curr_date}")
    
    result = get_global_market_news(curr_date=curr_date, look_back_days=7, limit=5)
    
    print("Success!")
    print(f"Result type: {type(result)}")
    if isinstance(result, str):
        print(f"Result preview: {result[:200]}...")
    else:
        print(f"Result keys: {result.keys() if isinstance(result, dict) else 'Not a dict'}")

except Exception as e:
    print(f"FAILED: {e}")
