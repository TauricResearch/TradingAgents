"""Alpha Vantage-based scanner data fetching (fallback for market movers only)."""

from typing import Annotated
from datetime import datetime
import json
from .alpha_vantage_common import _make_api_request


def get_market_movers_alpha_vantage(
    category: Annotated[str, "Category: 'day_gainers', 'day_losers', or 'most_actives'"]
) -> str:
    """
    Get market movers using Alpha Vantage TOP_GAINERS_LOSERS endpoint (fallback).
    
    Args:
        category: One of 'day_gainers', 'day_losers', or 'most_actives'
        
    Returns:
        Formatted string containing top market movers
    """
    try:
        # Alpha Vantage only supports top_gainers_losers endpoint
        # It doesn't have 'most_actives' directly
        if category not in ['day_gainers', 'day_losers', 'most_actives']:
            return f"Invalid category '{category}'. Must be one of: day_gainers, day_losers, most_actives"
        
        if category == 'most_actives':
            return "Alpha Vantage does not support 'most_actives' category. Please use yfinance instead."
        
        # Make API request for TOP_GAINERS_LOSERS endpoint
        response = _make_api_request("TOP_GAINERS_LOSERS", {})
        if isinstance(response, dict):
            data = response
        else:
            data = json.loads(response)
        
        if "Error Message" in data:
            return f"Error from Alpha Vantage: {data['Error Message']}"
        
        if "Note" in data:
            return f"Alpha Vantage API limit reached: {data['Note']}"
        
        # Map category to Alpha Vantage response key
        if category == 'day_gainers':
            key = 'top_gainers'
        elif category == 'day_losers':
            key = 'top_losers'
        else:
            return f"Unsupported category: {category}"
        
        if key not in data:
            return f"No data found for {category}"
        
        movers = data[key]
        
        if not movers:
            return f"No movers found for {category}"
        
        # Format the output
        header = f"# Market Movers: {category.replace('_', ' ').title()} (Alpha Vantage)\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        result_str = header
        result_str += "| Symbol | Price | Change % | Volume |\n"
        result_str += "|--------|-------|----------|--------|\n"
        
        for mover in movers[:15]:  # Top 15
            symbol = mover.get('ticker', 'N/A')
            price = mover.get('price', 'N/A')
            change_pct = mover.get('change_percentage', 'N/A')
            volume = mover.get('volume', 'N/A')
            
            # Format numbers
            if isinstance(price, str):
                try:
                    price = f"${float(price):.2f}"
                except ValueError:
                    price = "N/A"
            if isinstance(change_pct, str):
                change_pct = change_pct.rstrip('%')  # Remove % if present
            if isinstance(change_pct, (int, float)):
                change_pct = f"{float(change_pct):.2f}%"
            if isinstance(volume, (int, str)):
                try:
                    volume = f"{int(volume):,}"
                except ValueError:
                    volume = "N/A"
            
            result_str += f"| {symbol} | {price} | {change_pct} | {volume} |\n"
        
        return result_str
        
    except Exception as e:
        return f"Error fetching market movers from Alpha Vantage for {category}: {str(e)}"
