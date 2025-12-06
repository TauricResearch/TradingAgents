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


def get_earnings_calendar(
    from_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    to_date: Annotated[str, "End date in yyyy-mm-dd format"]
) -> str:
    """
    Get earnings calendar for stocks with upcoming earnings announcements.

    Args:
        from_date: Start date in yyyy-mm-dd format
        to_date: End date in yyyy-mm-dd format

    Returns:
        str: Formatted report of upcoming earnings
    """
    try:
        client = get_finnhub_client()
        data = client.earnings_calendar(
            _from=from_date,
            to=to_date,
            symbol="",  # Empty string returns all stocks
            international=False
        )

        if not data or 'earningsCalendar' not in data:
            return f"No earnings data found for period {from_date} to {to_date}"

        earnings = data['earningsCalendar']

        if not earnings:
            return f"No earnings scheduled between {from_date} and {to_date}"

        # Format the response
        result = f"## Earnings Calendar ({from_date} to {to_date})\n\n"
        result += f"**Total Companies**: {len(earnings)}\n\n"

        # Group by date
        by_date = {}
        for entry in earnings:
            date = entry.get('date', 'Unknown')
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(entry)

        # Format by date
        for date in sorted(by_date.keys()):
            result += f"### {date}\n\n"

            for entry in by_date[date]:
                symbol = entry.get('symbol', 'N/A')
                eps_estimate = entry.get('epsEstimate', 'N/A')
                eps_actual = entry.get('epsActual', 'N/A')
                revenue_estimate = entry.get('revenueEstimate', 'N/A')
                revenue_actual = entry.get('revenueActual', 'N/A')
                hour = entry.get('hour', 'N/A')

                result += f"**{symbol}**"
                if hour != 'N/A':
                    result += f" ({hour})"
                result += "\n"

                if eps_estimate != 'N/A':
                    result += f"  - EPS Estimate: ${eps_estimate:.2f}" if isinstance(eps_estimate, (int, float)) else f"  - EPS Estimate: {eps_estimate}"
                    if eps_actual != 'N/A':
                        result += f" | Actual: ${eps_actual:.2f}" if isinstance(eps_actual, (int, float)) else f" | Actual: {eps_actual}"
                    result += "\n"

                if revenue_estimate != 'N/A':
                    result += f"  - Revenue Estimate: ${revenue_estimate:,.0f}M" if isinstance(revenue_estimate, (int, float)) else f"  - Revenue Estimate: {revenue_estimate}"
                    if revenue_actual != 'N/A':
                        result += f" | Actual: ${revenue_actual:,.0f}M" if isinstance(revenue_actual, (int, float)) else f" | Actual: {revenue_actual}"
                    result += "\n"

                result += "\n"

        return result

    except Exception as e:
        return f"Error fetching earnings calendar: {str(e)}"


def get_ipo_calendar(
    from_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    to_date: Annotated[str, "End date in yyyy-mm-dd format"]
) -> str:
    """
    Get IPO calendar for upcoming and recent initial public offerings.

    Args:
        from_date: Start date in yyyy-mm-dd format
        to_date: End date in yyyy-mm-dd format

    Returns:
        str: Formatted report of IPOs
    """
    try:
        client = get_finnhub_client()
        data = client.ipo_calendar(
            _from=from_date,
            to=to_date
        )

        if not data or 'ipoCalendar' not in data:
            return f"No IPO data found for period {from_date} to {to_date}"

        ipos = data['ipoCalendar']

        if not ipos:
            return f"No IPOs scheduled between {from_date} and {to_date}"

        # Format the response
        result = f"## IPO Calendar ({from_date} to {to_date})\n\n"
        result += f"**Total IPOs**: {len(ipos)}\n\n"

        # Group by date
        by_date = {}
        for entry in ipos:
            date = entry.get('date', 'Unknown')
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(entry)

        # Format by date
        for date in sorted(by_date.keys()):
            result += f"### {date}\n\n"

            for entry in by_date[date]:
                symbol = entry.get('symbol', 'N/A')
                name = entry.get('name', 'N/A')
                exchange = entry.get('exchange', 'N/A')
                price = entry.get('price', 'N/A')
                shares = entry.get('numberOfShares', 'N/A')
                total_shares = entry.get('totalSharesValue', 'N/A')
                status = entry.get('status', 'N/A')

                result += f"**{symbol}** - {name}\n"
                result += f"  - Exchange: {exchange}\n"

                if price != 'N/A':
                    result += f"  - Price: ${price}\n"

                if shares != 'N/A':
                    result += f"  - Shares Offered: {shares:,}\n" if isinstance(shares, (int, float)) else f"  - Shares Offered: {shares}\n"

                if total_shares != 'N/A':
                    result += f"  - Total Value: ${total_shares:,.0f}M\n" if isinstance(total_shares, (int, float)) else f"  - Total Value: {total_shares}\n"

                result += f"  - Status: {status}\n\n"

        return result

    except Exception as e:
        return f"Error fetching IPO calendar: {str(e)}"
