from typing import Union, Dict, Optional
from .alpha_vantage_common import _make_api_request, format_datetime_for_api

def get_news(ticker: str = None, start_date: str = None, end_date: str = None, query: str = None) -> Union[Dict[str, str], str]:
    """Returns live and historical market news & sentiment data.

    Args:
        ticker: Stock symbol (deprecated, use query).
        start_date: Start date for news search.
        end_date: End date for news search.
        query: Search query or ticker symbol (preferred).

    Returns:
        Dictionary containing news sentiment data or JSON string.
    """
    # Handle parameter aliases
    target_query = query or ticker
    if not target_query:
        raise ValueError("Must provide query or ticker")

    params = {
        "tickers": target_query,
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(end_date),
        "sort": "LATEST",
        "limit": "50",
    }
    
    return _make_api_request("NEWS_SENTIMENT", params)


def get_global_news(date: str, look_back_days: int = 7, limit: int = 5) -> Union[Dict[str, str], str]:
    """Returns global market news & sentiment data.

    Args:
        date: Date for news search (yyyy-mm-dd).
        look_back_days: Days to look back (unused by AV but kept for interface).
        limit: Number of articles (unused by AV but kept for interface).

    Returns:
        Dictionary containing news sentiment data or JSON string.
    """
    params = {
        "topics": "finance,economy_macro",
        "time_from": format_datetime_for_api(date),
        "sort": "LATEST",
        "limit": "50",
    }

    return _make_api_request("NEWS_SENTIMENT", params)

def get_insider_transactions(symbol: str = None, ticker: str = None, curr_date: str = None) -> Union[Dict[str, str], str]:
    """Returns latest and historical insider transactions.

    Args:
        symbol: Ticker symbol.
        ticker: Alias for symbol.
        curr_date: Current date (unused).

    Returns:
        Dictionary containing insider transaction data or JSON string.
    """
    target_symbol = symbol or ticker
    if not target_symbol:
        raise ValueError("Must provide either symbol or ticker")

    params = {
        "symbol": target_symbol,
    }

    return _make_api_request("INSIDER_TRANSACTIONS", params)

def get_insider_sentiment(symbol: str = None, ticker: str = None, curr_date: str = None) -> str:
    """Returns insider sentiment data derived from Alpha Vantage transactions.
    
    Args:
        symbol: Ticker symbol.
        ticker: Alias for symbol.
        curr_date: Current date.
        
    Returns:
        Formatted string containing insider sentiment analysis.
    """
    target_symbol = symbol or ticker
    if not target_symbol:
        raise ValueError("Must provide either symbol or ticker")

    import json
    from datetime import datetime, timedelta
    
    # Fetch transactions
    params = {
        "symbol": target_symbol,
    }
    response_text = _make_api_request("INSIDER_TRANSACTIONS", params)
    
    try:
        data = json.loads(response_text)
        if "Information" in data:
            return f"Error: {data['Information']}"
            
        # Alpha Vantage INSIDER_TRANSACTIONS returns a dictionary with "symbol" and "data" (list)
        # or sometimes just the list depending on the endpoint version, but usually it's under a key.
        # Let's handle the standard response structure.
        # Based on docs, it returns CSV by default? No, _make_api_request handles JSON.
        # Actually, Alpha Vantage INSIDER_TRANSACTIONS returns JSON by default.
        
        # Structure check
        transactions = []
        if "data" in data:
            transactions = data["data"]
        elif isinstance(data, list):
            transactions = data
        else:
            # If we can't find the list, return the raw text
            return f"Raw Data: {str(data)[:500]}"
            
        # Filter and Aggregate
        # We want recent transactions (e.g. last 3 months)
        if curr_date:
            curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        else:
            curr_dt = datetime.now()
            
        start_dt = curr_dt - timedelta(days=90)
        
        relevant_txs = []
        for tx in transactions:
            # Date format in AV is usually YYYY-MM-DD
            try:
                tx_date_str = tx.get("transaction_date")
                if not tx_date_str:
                    continue
                tx_date = datetime.strptime(tx_date_str, "%Y-%m-%d")
                
                if start_dt <= tx_date <= curr_dt:
                    relevant_txs.append(tx)
            except ValueError:
                continue
                
        if not relevant_txs:
            return f"No insider transactions found for {symbol} in the 90 days before {curr_date}."
            
        # Calculate metrics
        total_bought = 0
        total_sold = 0
        net_shares = 0
        
        for tx in relevant_txs:
            shares = int(float(tx.get("shares", 0)))
            # acquisition_or_disposal: "A" (Acquisition) or "D" (Disposal)
            # transaction_code: "P" (Purchase), "S" (Sale)
            # We can use acquisition_or_disposal if available, or transaction_code
            
            code = tx.get("acquisition_or_disposal")
            if not code:
                # Fallback to transaction code logic if needed, but A/D is standard for AV
                pass
                
            if code == "A":
                total_bought += shares
                net_shares += shares
            elif code == "D":
                total_sold += shares
                net_shares -= shares
                
        sentiment = "NEUTRAL"
        if net_shares > 0:
            sentiment = "POSITIVE"
        elif net_shares < 0:
            sentiment = "NEGATIVE"
            
        report = f"## Insider Sentiment for {symbol} (Last 90 Days)\n"
        report += f"**Overall Sentiment:** {sentiment}\n"
        report += f"**Net Shares:** {net_shares:,}\n"
        report += f"**Total Bought:** {total_bought:,}\n"
        report += f"**Total Sold:** {total_sold:,}\n"
        report += f"**Transaction Count:** {len(relevant_txs)}\n\n"
        report += "### Recent Transactions:\n"
        
        # List top 5 recent
        relevant_txs.sort(key=lambda x: x.get("transaction_date", ""), reverse=True)
        for tx in relevant_txs[:5]:
            report += f"- {tx.get('transaction_date')}: {tx.get('executive')} - {tx.get('acquisition_or_disposal')} {tx.get('shares')} shares at ${tx.get('transaction_price')}\n"
            
        return report

    except Exception as e:
        return f"Error processing insider sentiment: {str(e)}\nRaw response: {response_text[:200]}"