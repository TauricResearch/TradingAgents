import os
import requests
from typing import Annotated
from dotenv import load_dotenv

load_dotenv()

def get_reuters_news(
    ticker: Annotated[str, "Ticker of a company. e.g. AAPL, TSM"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: int = 7
) -> str:
    """Get Reuters news for stock ticker"""

    try:
        api_key = os.getenv('REUTERS_API_KEY')
        if not api_key:
            return f"Reuters News: API credentials not configured"

        company_name = get_company_name(ticker)

        search_queries = [f"{ticker} stock", f"{company_name} earnings", f"{company_name} news"]
        news_items = []

        for query in search_queries:
            try:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }

                url = "https://api.reuters.com/v2/articles/search"

                params = {
                    'query': query,
                    'limit': 5,
                    'sortBy': 'publishedDateTime',
                    'sortOrder': 'desc'
                }

                response = requests.get(url, headers=headers, params=params)

                if response.status_code == 200:
                    data = response.json()
                    if data.get('data', {}).get('articles'):
                        for article in data['data']['articles'][:3]:
                            title = article.get('title', '')
                            summary = article.get('description', '')[:150]
                            category = article.get('category', {}).get('name', '')
                            if title and summary:
                                news_items.append(f"- [{category}] {title}: {summary}")

            except Exception:
                continue

        if news_items:
            return f"Reuters News for {ticker}:\n" + "\n".join(news_items[:8])
        else:
            try:
                from reuterspy import ReutersPy
                reuters = ReutersPy()

                company_data = reuters.get_company_info(ticker)
                if company_data:
                    return f"Reuters: {ticker} fundamental data available - {company_data[:200]}"
                else:
                    return f"Reuters News: No recent news found for {ticker}"

            except ImportError:
                return f"Reuters News: No recent news found for {ticker}"

    except Exception as e:
        return f"Reuters News: Service unavailable - {str(e)[:50]}"

def get_company_name(ticker: str) -> str:
    """Map ticker to company name for Reuters search"""
    ticker_mapping = {
        "AAPL": "Apple Inc",
        "MSFT": "Microsoft Corp",
        "GOOGL": "Alphabet Inc",
        "AMZN": "Amazon.com",
        "TSLA": "Tesla Inc",
        "NVDA": "NVIDIA Corp",
        "META": "Meta Platforms",
        "JPM": "JPMorgan Chase",
        "JNJ": "Johnson & Johnson",
        "V": "Visa Inc",
        "TSM": "Taiwan Semiconductor"
    }
    return ticker_mapping.get(ticker, ticker)