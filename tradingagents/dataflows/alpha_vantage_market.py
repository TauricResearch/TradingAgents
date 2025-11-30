from .alpha_vantage_common import _make_api_request
import csv
import io

def get_market_movers(
    metric: str = "top_gainers",
    limit: int = 10
) -> str:
    """
    Returns the top gainers, losers, or most active stocks from Alpha Vantage.

    Args:
        metric: One of "top_gainers", "top_losers", "most_actively_traded"
        limit: Number of results to return (default 10)

    Returns:
        CSV string containing the market movers data.
    """
    params = {}
    response = _make_api_request("TOP_GAINERS_LOSERS", params)
    
    # The response is JSON for this endpoint, not CSV
    # We need to parse it and convert to CSV format for consistency
    import json
    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        return f"Error parsing response: {response}"
    
    if metric not in data:
        return f"Metric '{metric}' not found in response. Available: {list(data.keys())}"
    
    items = data[metric]
    
    # Sort just in case, though API usually returns sorted
    # Note: "change_percentage" is a string like "10.5%", need to parse for sorting if needed
    # But usually the API returns them sorted.
    
    items = items[:limit]
    
    if not items:
        return f"No data found for metric '{metric}'"
        
    # Convert to CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    if items:
        writer.writerow(items[0].keys())
        
    for item in items:
        writer.writerow(item.values())
        
    return output.getvalue()

def get_earnings_calendar(
    horizon: str = "3month",
    symbol: str = None
) -> str:
    """
    Returns the earnings calendar for the specified horizon or symbol.

    Args:
        horizon: "3month", "6month", or "12month" (default "3month")
        symbol: Optional ticker symbol to filter by

    Returns:
        CSV string containing the earnings calendar.
    """
    params = {"horizon": horizon}
    if symbol:
        params["symbol"] = symbol
        
    response = _make_api_request("EARNINGS_CALENDAR", params)
    return response
