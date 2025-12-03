import os
import finnhub
from typing import Annotated
from dotenv import load_dotenv

load_dotenv()

def get_finnhub_client():
    """Get authenticated Finnhub client."""
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise ValueError("FINNHUB_API_KEY not found in environment variables.")
    return finnhub.Client(api_key=api_key)

def get_recommendation_trends(
    ticker: Annotated[str, "Ticker symbol of the company"]
) -> str:
    """
    Get analyst recommendation trends for a stock.
    Shows the distribution of buy/hold/sell recommendations over time.
    
    Args:
        ticker: Stock ticker symbol (e.g., "AAPL", "TSLA")
        
    Returns:
        str: Formatted report of recommendation trends
    """
    try:
        client = get_finnhub_client()
        data = client.recommendation_trends(ticker.upper())
        
        if not data:
            return f"No recommendation trends data found for {ticker}"
        
        # Format the response
        result = f"## Analyst Recommendation Trends for {ticker.upper()}\n\n"
        
        for entry in data:
            period = entry.get('period', 'N/A')
            strong_buy = entry.get('strongBuy', 0)
            buy = entry.get('buy', 0)
            hold = entry.get('hold', 0)
            sell = entry.get('sell', 0)
            strong_sell = entry.get('strongSell', 0)
            
            total = strong_buy + buy + hold + sell + strong_sell
            
            result += f"### {period}\n"
            result += f"- **Strong Buy**: {strong_buy}\n"
            result += f"- **Buy**: {buy}\n"
            result += f"- **Hold**: {hold}\n"
            result += f"- **Sell**: {sell}\n"
            result += f"- **Strong Sell**: {strong_sell}\n"
            result += f"- **Total Analysts**: {total}\n\n"
            
            # Calculate sentiment
            if total > 0:
                bullish_pct = ((strong_buy + buy) / total) * 100
                bearish_pct = ((sell + strong_sell) / total) * 100
                result += f"**Sentiment**: {bullish_pct:.1f}% Bullish, {bearish_pct:.1f}% Bearish\n\n"
        
        return result
        
    except Exception as e:
        return f"Error fetching recommendation trends for {ticker}: {str(e)}"
