from langchain_core.tools import tool
from typing import Annotated
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


def _get_nearest_expiry(ticker_obj, days_forward: int = 30) -> str:
    """
    Get the nearest options expiry date within days_forward days.
    If none found, returns the nearest available expiry.
    """
    try:
        expirations = ticker_obj.options
        if not expirations:
            return None
        
        today = datetime.now().date()
        target_date = today + timedelta(days=days_forward)
        
        # Convert string dates to datetime objects for comparison
        expiry_dates = [datetime.strptime(e, "%Y-%m-%d").date() for e in expirations]
        
        # Find expiry closest to target_date (but preferably in the future)
        future_dates = [d for d in expiry_dates if d >= today]
        if future_dates:
            # Get the closest date to target within the future dates
            nearest = min(future_dates, key=lambda x: abs((x - target_date).days))
            return nearest.strftime("%Y-%m-%d")
        
        # If no future dates, return the latest available
        return max(expirations)
    except Exception as e:
        return None


@tool
def get_options_chain(
    symbol: Annotated[str, "ticker symbol of the company"],
    expiry_date: Annotated[str, "options expiry date in yyyy-mm-dd format, or 'nearest' for closest expiry"] = "nearest",
) -> str:
    """
    Retrieve options chain data (calls and puts) for a given ticker symbol.
    Returns a formatted DataFrame containing call and put option details.
    
    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, MSFT
        expiry_date (str): Options expiry date in yyyy-mm-dd format, or 'nearest' for automatic selection
    
    Returns:
        str: Formatted options chain data with calls and puts, including strike prices, volumes, and open interest
    """
    try:
        # Fetch ticker data
        ticker = yf.Ticker(symbol.upper())
        
        # Get expiry date
        if expiry_date.lower() == "nearest":
            expiry = _get_nearest_expiry(ticker, days_forward=30)
            if not expiry:
                return f"No options data available for {symbol.upper()}. This ticker may not have listed options."
        else:
            expiry = expiry_date
        
        # Fetch options chain for the expiry date
        try:
            options_df = ticker.option_chain(expiry)
        except Exception as e:
            return f"Failed to fetch options chain for {symbol.upper()} with expiry {expiry}: {str(e)}"
        
        calls = options_df.calls
        puts = options_df.puts
        
        # Format calls
        calls_summary = _format_options_data(calls, "CALLS", symbol.upper(), expiry)
        
        # Format puts
        puts_summary = _format_options_data(puts, "PUTS", symbol.upper(), expiry)
        
        # Create combined summary
        summary = f"# Options Chain for {symbol.upper()} - Expiry: {expiry}\n"
        summary += f"Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        summary += calls_summary + "\n\n" + puts_summary
        
        return summary
    
    except Exception as e:
        return f"Error retrieving options chain for {symbol.upper()}: {str(e)}"


def _format_options_data(options_df: pd.DataFrame, option_type: str, symbol: str, expiry: str) -> str:
    """Helper function to format options data (calls or puts)."""
    if options_df.empty:
        return f"No {option_type} data available."
    
    # Select relevant columns
    columns_to_display = ["strike", "lastPrice", "volume", "openInterest", "impliedVolatility"]
    available_cols = [col for col in columns_to_display if col in options_df.columns]
    
    df_display = options_df[available_cols].copy()
    
    # Round numerical values
    for col in df_display.columns:
        if df_display[col].dtype in ['float64', 'float32']:
            df_display[col] = df_display[col].round(2)
    
    # Convert to CSV string
    csv_string = df_display.to_csv()
    
    header = f"\n## {option_type}\n"
    header += f"Total {option_type} contracts: {len(options_df)}\n"
    header += f"Strike range: ${options_df['strike'].min():.2f} - ${options_df['strike'].max():.2f}\n\n"
    
    return header + csv_string


@tool
def calculate_put_call_ratio(
    symbol: Annotated[str, "ticker symbol of the company"],
    expiry_date: Annotated[str, "options expiry date in yyyy-mm-dd format, or 'nearest' for closest expiry"] = "nearest",
    ratio_type: Annotated[str, "Type of ratio to calculate: 'volume' (volume-based) or 'oi' (open interest-based)"] = "volume",
) -> str:
    """
    Calculate put/call ratios for options on a given ticker symbol.
    Ratios help gauge market sentiment: higher ratios suggest bearish sentiment, lower suggest bullish.
    
    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, MSFT
        expiry_date (str): Options expiry date in yyyy-mm-dd format, or 'nearest' for automatic selection
        ratio_type (str): 'volume' for volume-based ratio, 'oi' for open interest-based ratio
    
    Returns:
        str: Formatted analysis of put/call ratios and their implications for market sentiment
    """
    try:
        # Fetch ticker data
        ticker = yf.Ticker(symbol.upper())
        
        # Get expiry date
        if expiry_date.lower() == "nearest":
            expiry = _get_nearest_expiry(ticker, days_forward=30)
            if not expiry:
                return f"No options data available for {symbol.upper()}. This ticker may not have listed options."
        else:
            expiry = expiry_date
        
        # Fetch options chain
        try:
            options_data = ticker.option_chain(expiry)
        except Exception as e:
            return f"Failed to fetch options chain for {symbol.upper()} with expiry {expiry}: {str(e)}"
        
        calls = options_data.calls
        puts = options_data.puts
        
        # Calculate ratios
        ratios = _compute_put_call_ratios(calls, puts, symbol.upper(), expiry, ratio_type)
        
        return ratios
    
    except Exception as e:
        return f"Error calculating put/call ratio for {symbol.upper()}: {str(e)}"


def _compute_put_call_ratios(calls: pd.DataFrame, puts: pd.DataFrame, symbol: str, expiry: str, ratio_type: str) -> str:
    """
    Compute put/call ratios from options data.
    Returns formatted analysis with sentiment implications.
    """
    result = f"\n# Put/Call Ratio Analysis for {symbol} - Expiry: {expiry}\n"
    result += f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    result += f"Ratio Type: {'Volume-Based' if ratio_type == 'volume' else 'Open Interest-Based'}\n\n"
    
    try:
        if ratio_type.lower() == "volume":
            total_put_volume = puts['volume'].sum()
            total_call_volume = calls['volume'].sum()
            
            if total_call_volume == 0:
                ratio = 0.0 if total_put_volume == 0 else float('inf')
            else:
                ratio = total_put_volume / total_call_volume
            
            result += f"## Volume-Based Ratio\n"
            result += f"Total Put Volume: {int(total_put_volume):,}\n"
            result += f"Total Call Volume: {int(total_call_volume):,}\n"
            result += f"**Put/Call Volume Ratio: {ratio:.4f}**\n\n"
            
        elif ratio_type.lower() == "oi":
            total_put_oi = puts['openInterest'].sum()
            total_call_oi = calls['openInterest'].sum()
            
            if total_call_oi == 0:
                ratio = 0.0 if total_put_oi == 0 else float('inf')
            else:
                ratio = total_put_oi / total_call_oi
            
            result += f"## Open Interest-Based Ratio\n"
            result += f"Total Put Open Interest: {int(total_put_oi):,}\n"
            result += f"Total Call Open Interest: {int(total_call_oi):,}\n"
            result += f"**Put/Call OI Ratio: {ratio:.4f}**\n\n"
        
        # Sentiment interpretation
        result += _interpret_put_call_ratio(ratio)
        
        # Additional metrics
        result += _compute_weighted_metrics(calls, puts, symbol)
        
        return result
    
    except Exception as e:
        return f"Error computing ratios: {str(e)}"


def _interpret_put_call_ratio(ratio: float) -> str:
    """Interpret put/call ratio and provide sentiment analysis."""
    interpretation = "\n## Sentiment Interpretation\n"
    
    if ratio == 0 or ratio == float('inf'):
        interpretation += "Insufficient data for ratio calculation (one side is zero).\n"
        return interpretation
    
    if ratio < 0.5:
        interpretation += f"**Bullish Signal (Ratio: {ratio:.4f})**\n"
        interpretation += "- Calls significantly outnumber puts\n"
        interpretation += "- Market participants are predominantly buying call options\n"
        interpretation += "- Suggests optimistic outlook and upside expectations\n"
        interpretation += "- Caution: May indicate euphoria; consider reversal risk\n"
    elif 0.5 <= ratio < 1.0:
        interpretation += f"**Moderately Bullish (Ratio: {ratio:.4f})**\n"
        interpretation += "- More calls than puts, but balanced\n"
        interpretation += "- Mixed sentiment with slight bullish lean\n"
        interpretation += "- Healthy market participation on both sides\n"
    elif 1.0 <= ratio < 1.5:
        interpretation += f"**Neutral to Moderately Bearish (Ratio: {ratio:.4f})**\n"
        interpretation += "- Roughly equal or slight put bias\n"
        interpretation += "- Market uncertain or slightly defensive\n"
        interpretation += "- Suggests caution and hedging activity\n"
    else:
        interpretation += f"**Bearish Signal (Ratio: {ratio:.4f})**\n"
        interpretation += "- Puts significantly outnumber calls\n"
        interpretation += "- Market participants buying protective puts\n"
        interpretation += "- Suggests defensive positioning and downside concerns\n"
        interpretation += "- May indicate fear; consider contrarian reversal potential\n"
    
    return interpretation


def _compute_weighted_metrics(calls: pd.DataFrame, puts: pd.DataFrame, symbol: str) -> str:
    """Compute additional weighted metrics for deeper analysis."""
    metrics = "\n## Detailed Metrics by Strike\n"
    
    try:
        # Get ATM (At-The-Money) strike - find strike closest to last price
        # Note: yfinance doesn't provide current price in option_chain, so we estimate from mid-price
        call_mids = (calls['bid'] + calls['ask']) / 2
        put_mids = (puts['bid'] + puts['ask']) / 2
        
        avg_price = (call_mids.mean() + put_mids.mean()) / 2
        atm_strike = calls['strike'].iloc[(calls['strike'] - avg_price).abs().argmin()]
        
        # Segment analysis
        itm_calls = calls[calls['strike'] <= atm_strike]
        otm_calls = calls[calls['strike'] > atm_strike]
        itm_puts = puts[puts['strike'] < atm_strike]
        otm_puts = puts[puts['strike'] >= atm_strike]
        
        metrics += f"Estimated ATM Strike: ${atm_strike:.2f}\n"
        metrics += f"ITM Calls Volume: {int(itm_calls['volume'].sum()):,} | OTM Calls: {int(otm_calls['volume'].sum()):,}\n"
        metrics += f"ITM Puts Volume: {int(itm_puts['volume'].sum()):,} | OTM Puts: {int(otm_puts['volume'].sum()):,}\n"
        metrics += f"\nITM Call/Put Ratio: {(itm_calls['volume'].sum() / itm_puts['volume'].sum() if itm_puts['volume'].sum() > 0 else 0):.4f}\n"
        metrics += f"OTM Call/Put Ratio: {(otm_calls['volume'].sum() / otm_puts['volume'].sum() if otm_puts['volume'].sum() > 0 else 0):.4f}\n"
        
        return metrics
    except Exception as e:
        return f"Could not compute weighted metrics: {str(e)}\n"
