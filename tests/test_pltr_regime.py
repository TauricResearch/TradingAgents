
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
from io import StringIO
from tradingagents.agents.utils.agent_utils import get_stock_data
from tradingagents.engines.regime_detector import RegimeDetector, MarketRegime

def verify_momentum_exception():
    print("🚀 VERIFYING PLTR MOMENTUM EXCEPTION...")
    
    ticker = "PLTR"
    start_date = "2024-01-01"
    end_date = "2025-01-11"
    
    print(f"Fetching PLTR data ({start_date} to {end_date})...")
    
    try:
        raw_data = get_stock_data.invoke({
            "symbol": ticker,
            "start_date": start_date,
            "end_date": end_date,
            "format": "csv"
        })
        
        if "Error" in raw_data:
            print(f"❌ DATA FETCH ERROR: {raw_data}")
            return

        df = pd.read_csv(StringIO(raw_data), comment='#')
        
        # Helper cleaning
        if 'Close' not in df.columns:
             col_map = {c.lower(): c for c in df.columns}
             if 'close' in col_map:
                 df.rename(columns={col_map['close']: 'Close'}, inplace=True)
                 
        if 'Close' not in df.columns:
            print("❌ 'Close' column missing.")
            return

        prices = df['Close']
        print(f"✅ Data Loaded: {len(prices)} rows.")
        
        # Calculate Volatility Manually to confirm test conditions
        returns = prices.pct_change().dropna()
        recent_returns = returns.tail(60) # Default window
        volatility = recent_returns.std() * (252 ** 0.5)
        
        print(f"🧐 ACTUAL VOLATILITY (60d): {volatility:.2%}")
        
        # RUN DETECTOR
        regime, metrics = RegimeDetector.detect_regime(prices)
        
        print(f"\n📊 DETECTED REGIME: {regime.value.upper()}")
        print(f"   Volatility: {metrics['volatility']:.2%}")
        print(f"   Trend Strength (ADX): {metrics['trend_strength']:.2f}")
        print(f"   Cumulative Return (Window): {metrics['cumulative_return']:.2%}")
        
        if regime == MarketRegime.TRENDING_UP:
            if metrics['volatility'] > 0.40:
                print("✅ SUCCESS: MOMENTUM EXCEPTION ACTIVATED! (High Vol + Strong Trend = TRENDING_UP)")
            else:
                print("ℹ️  Standard TRENDING_UP (Volatility below threshold).")
        elif regime == MarketRegime.VOLATILE:
            print("❌ FAILURE: Still classified as VOLATILE despite strong trend.")
        else:
            print(f"❌ UNEXPECTED REGIME: {regime.value}")

    except Exception as e:
        print(f"❌ TEST EXCEPTION: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_momentum_exception()
