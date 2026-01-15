
import pandas as pd
from io import StringIO
import datetime
from tradingagents.dataflows.y_finance import get_YFin_data_online

def test_parsing():
    print("--- 1. FETCHING REAL YFINANCE DATA ---")
    start = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    end = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Call the exact function used by Registrar
    raw_data = get_YFin_data_online("NVDA", start, end, format="csv")
    
    print(f"\n--- 2. RAW DATA SNIPPET ---\n{raw_data[:200]}...")
    
    print("\n--- 3. SIMULATING MARKET ANALYST PARSING ---")
    try:
        # Exact logic from market_analyst.py
        if isinstance(raw_data, str) and len(raw_data.strip()) > 50:
            print("Detected String Input...")
            df = pd.read_csv(StringIO(raw_data), comment='#')
            print(f"✅ Success! DataFrame Shape: {df.shape}")
            print(f"Columns: {df.columns.tolist()}")
            
            # Normalization Logic
            if 'Close' not in df.columns:
                 print("Attempting column normalization...")
                 col_map = {c.lower(): c for c in df.columns}
                 if 'close' in col_map:
                     df.rename(columns={col_map['close']: 'Close'}, inplace=True)
                     print("Renamed 'close' -> 'Close'")
            
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'])
                df.set_index('Date', inplace=True)
                print("Index set to Date")
                
            print(f"Final Index Type: {type(df.index)}")
            if len(df) > 5:
                print("✅ Sufficient Data for Regime Detection")
            else:
                print("❌ Insufficient Data (<5 rows)")
                
        else:
            print("❌ Input not recognized as valid CSV string.")

    except Exception as e:
        print(f"❌ CRASH during parsing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_parsing()
