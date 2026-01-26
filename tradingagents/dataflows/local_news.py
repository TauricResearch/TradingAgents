from datetime import date, timedelta, datetime
import json
import logging
import os

from .config import DATA_DIR

log = logging.getLogger(__name__)

def get_local_news(ticker, start_date: str, end_date: str) -> dict[str, str] | str:
    """Returns live and historical market news & sentiment data from premier news outlets worldwide.

    Covers stocks, cryptocurrencies, forex, and topics like fiscal policy, mergers & acquisitions, IPOs.

    Args:
        ticker: Stock symbol for news articles.
        start_date: Start date for news search.
        end_date: End date for news search.

    Returns:
        Dictionary containing news sentiment data or JSON string.
    """

    template = lambda feed: f"""{{
        "items": {len(feed)},
        "sentiment_score_definition": "x <= -0.65: Bearish; -0.65 < x <= -0.25: Somewhat-Bearish; -0.25 < x < 0.25: Neutral; 0.25 <= x < 0.65: Somewhat_Bullish; x >= 0.65: Bullish",
        "relevance_score_definition": "0 < x <= 1, with a higher score indicating higher relevance.",
        "feed": {feed}
    }}"""
    
    start_date_date = date.fromisoformat(start_date)
    end_date_date = date.fromisoformat(end_date)
    
    total_days = (end_date_date - start_date_date).days
    dates_to_fetch = [start_date_date + timedelta(days=i) for i in range(total_days)]
    
    feed = {}
    for date_ in dates_to_fetch:
        feed[str(date_)] = filter_irrelevant_news(load_news(ticker, date_))
    return template(feed)
    
def load_news(ticker: str, date: date, save_dir:str = 'news/daily_news_processed') -> list:
    """
    Load news articles from a JSON file.`
    
    Args:
        ticker (str): The stock ticker symbol.
        date (date_cls): The date for which to load news articles.
    Returns:
        list: A list of news articles loaded from the file.
    """
    save_dir = os.path.join(DATA_DIR, save_dir)
    filename = f"{save_dir}/{ticker}/{date}.json"
    try:
        with open(filename, 'r') as f:
            news = json.load(f)
        return news
    except Exception as e:
        print(f"Error loading news from {filename}: {e}")
        return []
    
def filter_irrelevant_news(news_list: list, threshold: float = 0.6) -> list:
    """
    Filter news articles based on their relevancy score.

    Args:
        news_list (list): List of news articles with relevancy scores.
        threshold (float): Minimum relevancy score to include a news article (default: 0.5).

    Returns:
        list: Filtered list of news articles with relevancy scores >= threshold.
    """
    try:
        if news_list is None or len(news_list) == 0:
            log.info("No news articles provided for filtering.")
            return []
        filtered_news = []
        for news in news_list:
            if 'relevancy_score' in news:
                if isinstance(news['relevancy_score'], (float, int)) and news['relevancy_score'] >= threshold:
                    filtered_news.append(
                        {
                            "summary": news.get("summary", ""),
                            "relevancy_score": news.get("relevancy_score", 0),
                            "sentiment_score": news.get("sentiment_score", 0)
                        }
                    )
            else:
                log.warning(f"News item missing valid 'relevancy_score': {news}")
        log.info(f"Filtered {len(filtered_news)} out of {len(news_list)} news articles with relevancy_score >= {threshold}.")
    except Exception as e:
        log.error(f"Error filtering news: {e}")
        filtered_news = news_list
    return filtered_news