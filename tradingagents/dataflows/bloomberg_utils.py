import os
import requests
from typing import Annotated
from dotenv import load_dotenv

load_dotenv()

def get_bloomberg_news(
    ticker: Annotated[str, "Ticker of a company. e.g. AAPL, TSM"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: int = 7
) -> str:
    """Get Bloomberg news for stock ticker"""

    try:
        api_key = os.getenv('BLOOMBERG_API_KEY')
        if not api_key:
            return f"Bloomberg News: API credentials not configured"

        company_name = get_company_name(ticker)

        search_terms = [ticker, company_name]
        news_items = []

        for term in search_terms:
            try:
                headers = {"Authorization": f"Bearer {api_key}"}
                url = "https://api.bloomberg.com/v1/news/search"

                params = {
                    'q': term,
                    'limit': 10,
                    'sort': 'publishedAt:desc'
                }

                response = requests.get(url, headers=headers, params=params)

                if response.status_code == 200:
                    data = response.json()
                    if data.get('articles'):
                        for article in data['articles'][:5]:
                            headline = article.get('headline', '')
                            summary = article.get('summary', '')[:200]
                            news_items.append(f"- {headline}: {summary}")

            except Exception:
                continue

        if news_items:
            return f"Bloomberg News for {ticker}:\n" + "\n".join(news_items[:10])
        else:
            return f"Bloomberg News: No recent news found for {ticker}"

    except Exception as e:
        return f"Bloomberg News: Service unavailable - {str(e)[:50]}"

def get_company_name(ticker: str) -> str:
    """Map ticker to company name for better search results"""
    ticker_mapping = {
        "AAPL": "Apple Inc",
        "MSFT": "Microsoft Corporation",
        "GOOGL": "Alphabet Google",
        "AMZN": "Amazon.com Inc",
        "TSLA": "Tesla Inc",
        "NVDA": "NVIDIA Corporation",
        "META": "Meta Facebook",
        "JPM": "JPMorgan Chase",
        "JNJ": "Johnson & Johnson",
        "V": "Visa Inc",
        "TSM": "Taiwan Semiconductor"
    }
    return ticker_mapping.get(ticker, ticker)