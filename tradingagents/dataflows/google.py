from typing import Annotated, List, Dict, Any
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from .googlenews_utils import getNewsData


def get_google_news(
    query: Annotated[str, "Query to search with"],
    curr_date: Annotated[str, "Curr date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    query = query.replace(" ", "+")

    start_date = datetime.strptime(curr_date, "%Y-%m-%d")
    before = start_date - relativedelta(days=look_back_days)
    before = before.strftime("%Y-%m-%d")

    news_results = getNewsData(query, before, curr_date)

    news_str = ""

    for news in news_results:
        news_str += (
            f"### {news['title']} (source: {news['source']}) \n\n{news['snippet']}\n\n"
        )

    if len(news_results) == 0:
        return ""

    return f"## {query} Google News, from {before} to {curr_date}:\n\n{news_str}"


def get_bulk_news_google(lookback_hours: int) -> List[Dict[str, Any]]:
    end_date = datetime.now()
    start_date = end_date - timedelta(hours=lookback_hours)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    queries = [
        "stock market",
        "trading news",
        "earnings report",
    ]

    all_articles = []
    seen_titles = set()

    for query in queries:
        try:
            news_results = getNewsData(query.replace(" ", "+"), start_str, end_str)

            for news in news_results:
                title = news.get("title", "")
                if title and title not in seen_titles:
                    seen_titles.add(title)

                    date_str = news.get("date", "")
                    try:
                        if date_str:
                            published_at = datetime.now()
                        else:
                            published_at = datetime.now()
                    except ValueError:
                        published_at = datetime.now()

                    article = {
                        "title": title,
                        "source": news.get("source", "Google News"),
                        "url": news.get("link", ""),
                        "published_at": published_at.isoformat(),
                        "content_snippet": news.get("snippet", "")[:500],
                    }
                    all_articles.append(article)

        except Exception:
            continue

    return all_articles
