import os
from dotenv import load_dotenv
from tradingagents.dataflows.alpaca import get_stock_data

# Load environment variables
load_dotenv()

def verify_alpaca():
    print("Locked & Loaded: Verifying Alpaca Data Connection...")
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_API_SECRET")
    
    if not api_key or not secret_key:
        print("❌ SKIPPING: ALPACA_API_KEY or ALPACA_API_SECRET not found in environment.")
        print("Please add them to your .env file to enable Alpaca.")
        return

    try:
        # Test with a known ticker
        symbol = "AAPL"
        print(f"Fetching data for {symbol}...")
        data = get_stock_data(symbol)
        
        if "Error" in data and not "No data found" in data:
            print(f"❌ FAIL: {data}")
        else:
            print("✅ SUCCESS: Data retrieved successfully!")
            rows = data.splitlines()[:5]
            print(f"Preview:\n" + "\n".join(rows) + "...")
            
    except Exception as e:
        print(f"❌ FAIL: Exception occurred: {e}")

if __name__ == "__main__":
    verify_alpaca()
