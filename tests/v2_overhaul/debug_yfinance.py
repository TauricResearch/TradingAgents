
import yfinance as yf
import pandas as pd

ticker = "GOOGL"
print(f"Fetching data for {ticker}...")
# Mimic DataRegistrar/interface logic
data = yf.download(ticker, period="1mo", interval="1d")

print("\n--- DataFrame Info ---")
print(data.info())

print("\n--- Columns ---")
print(data.columns)

print("\n--- Head ---")
print(data.head())

# Check for MultiIndex
if isinstance(data.columns, pd.MultiIndex):
    print("\n[CRITICAL] DataFrame has MultiIndex columns!")
    print("Levels:", data.columns.nlevels)
else:
    print("\n[OK] Single Index columns.")

# Simulate Market Analyst Logic

print("\n--- Market Analyst Logic Logic ---")
if 'Close' in data.columns:
    print("Direct 'Close' found.")
    price_data = data['Close']
    print(f"Type of data['Close']: {type(price_data)}")
    print(f"Shape of data['Close']: {price_data.shape}")
    
    if isinstance(price_data, pd.DataFrame):
        print("ALERT: data['Close'] is a DataFrame! MarketAnalyst might expect Series.")
        if price_data.shape[1] == 1:
            print("It has 1 column. Flattening...")
            price_data = price_data.iloc[:, 0]
            print(f"New Type: {type(price_data)}")
            
else:
    print("Direct 'Close' NOT found.")
