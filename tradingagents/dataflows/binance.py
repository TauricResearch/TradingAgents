from binance_common.configuration import ConfigurationRestAPI
from binance_common.constants import SPOT_REST_API_PROD_URL
from binance_sdk_spot.spot import Spot
from datetime import datetime
import csv
import io
from tradingagents.dataflows.config import get_config
from tradingagents.config import settings

_client = None

def get_binance_client():
    """Get or create Binance client with lazy initialization."""
    global _client
    if _client is None:
        try:
            api_key = settings.BINANCE_API_KEY
            if not api_key:
                raise ValueError("BINANCE_API_KEY not found in configuration")
            
            configuration = ConfigurationRestAPI(
                api_key=api_key, 
                base_path=SPOT_REST_API_PROD_URL
            )
            _client = Spot(config_rest_api=configuration)
        except Exception as e:
            print(f"ERROR: Failed to initialize Binance client: {e}")
            raise
    
    return _client

def get_market_data(symbol: str, start_date: str, end_date: str):
    """Fetch market data for a given symbol from Binance. Get OHLCV data. interval is 1 day.
    
    Args:
        symbol: Trading symbol (e.g., 'BTC/USDT')
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    
    Returns:
        CSV formatted string with OHLCV data
    """
    # remove / from symbol for binance format
    formatted_symbol = symbol.replace("/", "")

    # Convert dates to epoch time (milliseconds)
    start_epoch = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
    end_epoch = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
    
    # print(f"DEBUG: Fetching data for {formatted_symbol} from {start_date} to {end_date}")
    try:
        client = get_binance_client()
        response = client.rest_api.klines(
            symbol=formatted_symbol,
            start_time=start_epoch,
            end_time=end_epoch,
            interval="1d",
        )

        rate_limits = response.rate_limits
        # print(f"DEBUG: klines() rate limits: {rate_limits}")

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
        
        title = f"# Market Data for {symbol} from {start_date} to {end_date}\n\n"
        csv_string = title + csv_string
        return csv_string
        
    except Exception as e:
        print(f"ERROR: klines() error: {e}")
        return f"Error fetching market data from Binance: {e}"

