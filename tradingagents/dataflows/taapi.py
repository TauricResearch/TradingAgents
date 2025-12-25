import requests
from typing import Annotated
import os
from tradingagents.dataflows.config import get_config


def get_api_key() -> str:
    """Retrieve the API key for TAAPI from environment variables."""
    api_key = os.getenv("TAAPI_API_KEY")
    if not api_key:
        raise ValueError("TAAPI_API_KEY environment variable is not set.")
    return api_key


def get_crypto_stats_indicators_window(
    symbol: Annotated[str, "ticker symbol of the coin/asset"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[
        str, "The current trading date you are trading on, YYYY-mm-dd"
    ],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """Fetch technical indicator data from TAAPI.io for a given symbol.

    Args:
        symbol: Ticker symbol of the coin/asset (e.g., 'BTC/USDT')
        indicator: Technical indicator to get the analysis and report of (e.g., 'rsi', 'macd', 'sma', 'bbands', 'atr')
        curr_date: The current trading date you are trading on, in YYYY-MM-DD format
        look_back_days: How many days to look back
    Returns:
        str: A formatted report containing the technical indicators for the specified ticker symbol and indicator.
    """
    
    # Supported indicators mapping
    supported_indicators = {
        "sma": "Simple Moving Average",
        "macd": "MACD (Moving Average Convergence Divergence)",
        "rsi": "Relative Strength Index",
        "bbands": "Bollinger Bands",
        "atr": "Average True Range"
    }
    
    # Detailed indicator descriptions and usage
    indicator_descriptions = {
        "sma": "SMA (Simple Moving Average): A basic trend-following indicator that smooths out price data. Usage: Identify trend direction and serve as dynamic support/resistance levels. Tips: Use multiple SMAs for crossover signals; combines well with volume analysis for confirmation.",
        
        "macd": "MACD: Measures momentum via differences between fast and slow EMAs. Usage: Look for signal line crossovers, centerline crossovers, and divergence patterns for trend changes. Tips: Most effective in trending markets; combine with RSI to avoid false signals in sideways markets.",
        
        "rsi": "RSI: Oscillator measuring momentum to identify overbought (>70) and oversold (<30) conditions. Usage: Look for reversal signals at extreme levels and divergence with price action. Tips: In strong trends, RSI can remain extreme for extended periods; always confirm with trend analysis.",
        
        "bbands": "Bollinger Bands: Volatility indicator consisting of upper, middle (SMA), and lower bands based on standard deviations. Usage: Identify overbought/oversold conditions, volatility expansion/contraction, and potential breakout zones. Tips: Price touching bands doesn't guarantee reversal; use band squeeze for volatility breakout trades.",
        
        "atr": "ATR: Measures market volatility by calculating the average of true ranges over a period. Usage: Set stop-loss levels, position sizing, and identify high/low volatility periods for strategy adjustment. Tips: Higher ATR indicates more volatile conditions; use for risk management rather than directional signals."
    }
    
    # Validate indicator
    if indicator.lower() not in supported_indicators:
        return f"Error: Indicator '{indicator}' is not supported. Please choose from: {list(supported_indicators.keys())}"

    config = get_config()
    base_url = config["tool_providers"].get("TAAPI_BASE_URL", "https://api.taapi.io")
    api_key = get_api_key()

    # Set backtrack as requested
    backtrack = look_back_days

    # Construct the API URL
    url = f"{base_url}/{indicator.lower()}"

    # Set up parameters for the API call
    params = {
        "secret": api_key,
        "exchange": "binance",  # Default to binance exchange for crypto
        "symbol": symbol,
        "interval": "1d",  # Daily interval
        "backtrack": backtrack
    }

    try:
        # Make the API request
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise an exception for bad status codes

        # Get the JSON response
        data = response.json()

        # Format the response based on indicator type
        if isinstance(data, list):
            # Handle historical data (multiple periods)
            result_str = f"## {supported_indicators[indicator.lower()]} ({indicator.upper()}) for {symbol}:\n\n"
            
            for i, period_data in enumerate(data):
                if isinstance(period_data, dict):
                    result_str += f"Period {i + 1}:\n"
                    for key, value in period_data.items():
                        clean_key = key.replace("value", "").replace("Value", "")
                        if isinstance(value, (int, float)):
                            result_str += f"  {clean_key}: {value:.4f}\n"
                        else:
                            result_str += f"  {clean_key}: {value}\n"
                    result_str += "\n"
                    
        elif isinstance(data, dict):
            # Handle single period data
            result_str = f"## {supported_indicators[indicator.lower()]} ({indicator.upper()}) for {symbol}:\n\n"
            result_str += f"Current Date: {curr_date}\n"
            result_str += f"Lookback Days: {look_back_days}\n\n"
            
            # Generic formatting for all indicators
            for key, value in data.items():
                clean_key = key.replace("value", "").replace("Value", "")
                if isinstance(value, (int, float)):
                    result_str += f"{clean_key}: {value:.4f}\n"
                else:
                    result_str += f"{clean_key}: {value}\n"
        else:
            result_str = f"## {supported_indicators[indicator.lower()]} for {symbol}:\n{str(data)}"

        # Add the indicator description
        result_str += f"\n\n{indicator_descriptions.get(indicator.lower(), 'No description available.')}"
        
        return result_str

    except requests.exceptions.RequestException as e:
        return f"Error fetching data from TAAPI.io: {str(e)}"
    except ValueError as e:
        return f"Error parsing response from TAAPI.io: {str(e)}"
    except KeyError as e:
        return f"Error: Missing expected field in API response: {str(e)}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"
