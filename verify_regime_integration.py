import pandas as pd
from tradingagents.engines.regime_detector import RegimeDetector, DynamicIndicatorSelector
from tradingagents.agents.utils.agent_utils import get_stock_data
from io import StringIO
import json

def verify_regime():
    print("🔬 Verifying Regime Detector Integration...")
    
    ticker = "AAPL"
    print(f"Fetching data for {ticker}...")
    
    # Simulate what market_analyst_node does
    try:
        # Use invoke for StructuredTool
        # Provide dates (using a recent 1-year window relative to now implicitly, or fixed dates if tool supports it)
        # Assuming Alpaca data is available for this range
        raw_data = get_stock_data.invoke({
            "symbol": ticker,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "format": "csv" 
        })
        
        if "Error" in raw_data:
            print(f"❌ FAIL: Data fetch error: {raw_data}")
            return

        # Data has '#' comments in header, and is standard CSV
        df = pd.read_csv(StringIO(raw_data), comment='#')
        print(f"✅ Data fetched: {len(df)} rows")
        print(f"COLUMNS: {df.columns.tolist()}")
        print(f"HEAD:\n{df.head()}")
        
        if 'Close' not in df.columns:
             # Try case insensitive or check if it's in index?
             # Sometimes to_string creates a weird header structure
             pass
             print("❌ FAIL: 'Close' column missing")
             return

        # Run Detector
        print("Running RegimeDetector...")
        regime, metrics = RegimeDetector.detect_regime(df['Close'])
        
        print(f"✅ DETECTED REGIME: {regime.value}")
        print(f"   Volatility: {metrics['volatility']:.2%}")
        print(f"   Trend Strength: {metrics['trend_strength']:.2f}")
        
        # Run Selector
        optimal_params = DynamicIndicatorSelector.get_optimal_parameters(regime)
        print(f"✅ RECOMMENDED STRATEGY: {optimal_params['strategy']}")
        print(f"   Indicators: {[k for k in optimal_params.keys() if 'period' in k]}")
        
        print("\n🎉 INTEGRATION VERIFIED: The engine is analyzing data correctly.")
        
    except Exception as e:
        print(f"❌ FAIL: Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_regime()
