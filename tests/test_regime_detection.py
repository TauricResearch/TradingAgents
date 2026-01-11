import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
from io import StringIO
from datetime import datetime, timedelta
import yfinance as yf
from tradingagents.engines.regime_detector import RegimeDetector, DynamicIndicatorSelector

def test_regime_detection():
    print("🧪 Testing Regime Detection for PLTR...")
    
    ticker = "PLTR"
    current_date = "2026-01-11"
    
    # Simulate the same logic as market_analyst_node
    dt_obj = datetime.strptime(current_date, "%Y-%m-%d")
    start_date = (dt_obj - timedelta(days=365)).strftime("%Y-%m-%d")
    
    print(f"   Fetching data from {start_date} to {current_date}")
    
    # 1. Fetch raw data (simulating the tool call)
    ticker_obj = yf.Ticker(ticker)
    data = ticker_obj.history(start=start_date, end=current_date)
    
    if data.empty:
        print("❌ FAILURE: No data retrieved from yfinance.")
        return

    # Check columns
    print(f"   Columns found: {list(data.columns)}")
    
    # 2. Detect Regime
    try:
        prices = data['Close']
        regime, metrics = RegimeDetector.detect_regime(prices)
        print(f"✅ SUCCESS: Regime detected: {regime.value}")
        print(f"   Metrics: {metrics}")
        
        # Check if it matches 'trending_up' (as it should for PLTR in this hypothetical 2026 bull scenario)
        if regime.value == "trending_up":
            print("🌟 PLTR is in a BULL TREND.")
    except Exception as e:
        print(f"❌ FAILURE: Regime detection failed: {e}")

if __name__ == "__main__":
    test_regime_detection()
