
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
from io import StringIO
from tradingagents.agents.utils.agent_utils import get_stock_data
from tradingagents.engines.regime_detector import RegimeDetector

def verify_macro_regime():
    print("🌍 VERIFYING MACRO ENVIRONMENT DETECTION (PLTR CONTEXT)...")
    
    # We test SPY as proxy for "Broader Regime"
    macro_ticker = "SPY"
    print(f"\n1. Fetching Proxy Data for Broader Market ({macro_ticker})...")
    
    try:
        # Fetch 1 year of data
        raw_data = get_stock_data.invoke({
            "symbol": macro_ticker,
            "start_date": "2025-01-01",
            "end_date": "2026-01-11",
            "format": "csv"
        })
        
        if "Error" in raw_data or "No data" in raw_data:
            print(f"❌ MACRO FAIL: Could not fetch data for {macro_ticker}. Result: {raw_data[:100]}")
            return

        df = pd.read_csv(StringIO(raw_data), comment='#')
        
        if 'Close' not in df.columns:
             # Try case insensitive fallback
             col_map = {c.lower(): c for c in df.columns}
             if 'close' in col_map:
                 df.rename(columns={col_map['close']: 'Close'}, inplace=True)
        
        if 'Close' in df.columns and len(df) > 10:
            print(f"✅ Data fetched: {len(df)} rows")
            
            # DETECT REGIME
            print(f"   Running RegimeDetector for {macro_ticker}...")
            regime, metrics = RegimeDetector.detect_regime(df['Close'])
            
            print(f"\n📊 BROADER MARKET REGIME ({macro_ticker}): {regime.value}")
            print(f"   Volatility: {metrics['volatility']:.2%}")
            print(f"   Trend Strength (ADX): {metrics['trend_strength']:.2f}")
            print(f"   Hurst Exponent: {metrics['hurst_exponent']:.2f}")
            print(f"   Overall Return: {metrics.get('overall_return', 0):.2%}")
            
            if regime.value == "UNKNOWN":
                print("⚠️  Warning: Regime is UNKNOWN (likely insufficient history or data quality)")
            else:
                print("✅ MACRO REGIME SUCCESSFULLY IDENTIFIED.")
                
        else:
            print(f"❌ MACRO FAIL: insufficient data columns or rows. Cols: {df.columns.tolist()}")

    except Exception as e:
        print(f"❌ MACRO FAIL: Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_macro_regime()
