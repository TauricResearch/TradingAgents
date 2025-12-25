from binance_common.configuration import ConfigurationRestAPI
from binance_common.constants import SPOT_REST_API_PROD_URL
from binance_sdk_spot.spot import Spot
import os
from datetime import datetime
import csv
import io

def get_api_key() -> str:
    """Retrieve the API key for Binance from environment variables."""
    api_key = os.getenv("BINANCE_API_KEY")
    if not api_key:
        raise ValueError("BINANCE_API_KEY environment variable is not set.")
    return api_key

configuration = ConfigurationRestAPI(api_key=get_api_key(), base_path=SPOT_REST_API_PROD_URL)
client = Spot(config_rest_api=configuration)

def get_market_data(symbol: str, start_date: str, end_date: str):
    """Fetch market data for a given symbol from Binance. Get OHLCV data. interval is 1 day.
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSDT')
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    
    Returns:
        CSV formatted string with OHLCV data
    """
    # Convert dates to epoch time (milliseconds)
    start_epoch = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
    end_epoch = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
    
    print(f"DEBUG: Fetching data for {symbol} from {start_date} to {end_date}")
    try:
        response = client.rest_api.klines(
            symbol=symbol,
            start_time=start_epoch,
            end_time=end_epoch,
            interval="1d",
        )

        rate_limits = response.rate_limits
        print(f"DEBUG: klines() rate limits: {rate_limits}")

        data = response.data()
        
        # Convert to CSV format
        if not data:
            return "No data available"
        
        # Create CSV string
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        headers = [
            "Open Time",
            "Open Price", 
            "High Price",
            "Low Price",
            "Close Price",
            "Volume",
            "Close Time",
            "Quote Asset Volume",
            "Number of Trades",
            "Taker Buy Base Asset Volume",
            "Taker Buy Quote Asset Volume",
            "Unused Field"
        ]
        writer.writerow(headers)
        
        # Write data rows
        for row in data:
            writer.writerow(row)
        
        csv_string = output.getvalue()
        output.close()
        
        return csv_string
        
    except Exception as e:
        print(f"ERROR: klines() error: {e}")
        return f"Error fetching market data from Binance: {e}"

