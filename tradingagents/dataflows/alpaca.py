import os
import requests
import pandas as pd
from typing import Optional
from datetime import datetime, timedelta

def get_stock_data(symbol: str, start_date: str = None, end_date: str = None, format: str = "csv") -> str:
    """
    Fetch historical stock data (OHLCV) from Alpaca Data API v2.
    
    Args:
        symbol: Ticker symbol (e.g., "AAPL")
        start_date: Start date (YYYY-MM-DD), defaults to 1 year ago
        end_date: End date (YYYY-MM-DD), defaults to today
        format: Output format "string" (human readable) or "csv" (machine readable). Defaults to "csv".
        
    Returns:
        String representation of the dataframe
    """
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_API_SECRET")
    
    if not api_key or not secret_key:
        raise ValueError("Error: ALPACA_API_KEY and ALPACA_API_SECRET environment variables must be set.")
        
    # Default dates
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        
    # Alpaca API URL (Data API v2)
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
    
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key
    }
    
    params = {
        "start": start_date,
        "end": end_date,
        "timeframe": "1Day",
        "limit": 10000,
        "adjustment": "all", # Split and dividend adjusted
        "feed": "sip" # Use SIP feed if available, or 'iex' for free tier
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            # Check for free tier specific error regarding feed (422 or 403)
            # 422: Invalid value (explicit feed req)
            # 403: Forbidden (subscription level)
            if (response.status_code in [403, 422]) and ("feed" in response.text or "subscription" in response.text):
                 # Retry with IEX feed (Free tier)
                 print(f"INFO: Retrying {symbol} with IEX feed (Free Tier)...")
                 params["feed"] = "iex"
                 response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            raise ValueError(f"Alpaca API Error: {response.status_code} - {response.text}")
            
        data = response.json()
        
        if "bars" not in data or not data["bars"]:
            raise ValueError(f"No existing data for {symbol} on Alpaca between {start_date} and {end_date}.")
            
        # Parse data
        # Alpaca returns: t (time), o, h, l, c, v, nw, n
        bars = data["bars"]
        
        df_data = []
        for bar in bars:
            df_data.append({
                "Date": bar["t"].split("T")[0],
                "Open": bar["o"],
                "High": bar["h"],
                "Low": bar["l"],
                "Close": bar["c"],
                "Volume": bar["v"]
            })
            
        df = pd.DataFrame(df_data)
        
        # Format output string similar to yfinance output for consistency
        result_str = f"# Stock Data for {symbol} from {start_date} to {end_date}\n"
        
        if format.lower() == "csv":
            result_str += df.to_csv(index=False)
        else:
            result_str += df.to_string(index=False)
        
        return result_str
        
    except Exception as e:
        return f"Error fetching data from Alpaca for {symbol}: {str(e)}"
