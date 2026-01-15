
import pandas as pd
from io import StringIO
import logging

# Configure minimal logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DebugParsers")

def _calculate_net_insider_flow(raw_data: str) -> float:
    """Calculate net insider transaction value from report string."""
    try:
        print(f"DEBUG: Processing Raw Data Length: {len(raw_data)}")
        if not raw_data or "Error" in raw_data or "No insider" in raw_data:
            print("DEBUG: Early Exit (Error/Empty)")
            return 0.0
            
        # Robust CSV parsing
        try:
            # Simulate exactly what passes for 'comment'
            df = pd.read_csv(StringIO(raw_data), comment='#')
        except:
             # Fallback for messy data
             print("DEBUG: Fallback CSV Parsing used")
             df = pd.read_csv(StringIO(raw_data), sep=None, engine='python', comment='#')
        
        print("DEBUG: Columns found:", df.columns.tolist())
        
        # Standardize columns
        df.columns = [c.strip().lower() for c in df.columns]
        
        print("DEBUG: Normalized Columns:", df.columns.tolist())
        
        if 'value' not in df.columns:
            print("DEBUG: 'value' column missing!")
            return 0.0
            
        net_flow = 0.0
        
        # Iterate and sum
        for idx, row in df.iterrows():
            # Check for sale/purchase in text or other columns
            text = str(row.get('text', '')).lower() + str(row.get('transaction', '')).lower()
            val = float(row['value']) if pd.notnull(row['value']) else 0.0
            
            print(f"DEBUG Row {idx}: Text='{text}' | Value={val}")
            
            if 'sale' in text or 'sold' in text:
                print(f" -> Detected SALE: -{val}")
                net_flow -= val
            elif 'purchase' in text or 'buy' in text or 'bought' in text:
                print(f" -> Detected BUY: +{val}")
                net_flow += val
            else:
                print(" -> NO ACTION DETECTED")
                
        return net_flow
    except Exception as e:
        logger.warning(f"Failed to parse insider flow: {e}")
        return 0.0

if __name__ == "__main__":
    # Test Case 1: yfinance style output with comments
    csv_payload = """# Insider Transactions data for ASSET_200
# Data retrieved on: 2026-01-15 06:48:49

,Shares,Value,URL,Text,Insider,Position,Transaction,Start Date,Ownership
0,200000,37563619,,Sale at price 187.25 - 188.58 per share.,PURI AJAY K,Officer,,2026-01-07,I
1,80000,15187742,,Sale at price 188.85 - 192.49 per share.,Huang Jen-Hsun,Director,,2026-01-07,D
"""

    print("--- RUNNING TEST ---")
    flow = _calculate_net_insider_flow(csv_payload)
    print(f"--- RESULT: ${flow:,.2f} ---")
