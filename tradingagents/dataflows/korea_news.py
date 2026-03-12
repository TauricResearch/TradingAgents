"""Korean news data source using Naver Finance API and web scraping.

Provides Korean financial news, company-specific news, and macro news
relevant to the Korean market.
"""

import requests
from datetime import datetime, timedelta
from typing import Annotated
from dateutil.relativedelta import relativedelta


# Naver Search API headers (user should set NAVER_CLIENT_ID and NAVER_CLIENT_SECRET env vars)
_NAVER_HEADERS = None


def _get_naver_headers():
    """Get Naver API headers, lazy-loaded."""
    global _NAVER_HEADERS
    if _NAVER_HEADERS is None:
        import os

        client_id = os.environ.get("NAVER_CLIENT_ID", "")
        client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
        if client_id and client_secret:
            _NAVER_HEADERS = {
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
            }
        else:
            _NAVER_HEADERS = {}
    return _NAVER_HEADERS


def _get_stock_name_from_code(code: str) -> str:
    """Try to resolve stock name from code for better news search."""
    try:
        import FinanceDataReader as fdr

        listing = fdr.StockListing("KRX")
        if listing is not None and not listing.empty:
            match = listing[listing["Code"] == code]
            if match.empty:
                match = listing[listing["Symbol"] == code]
            if not match.empty:
                return match.iloc[0].get("Name", code)
    except Exception:
        pass
    return code


def get_korean_news(
    ticker: Annotated[str, "KRX ticker symbol or company name"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve Korean financial news for a specific stock.

    Uses Naver Search API if credentials are available, otherwise falls back
    to RSS-based news fetching.
    """
    # Try to resolve ticker to company name for better search
    company_name = ticker
    if ticker.isdigit():
        company_name = _get_stock_name_from_code(ticker)

    headers = _get_naver_headers()

    if headers:
        return _fetch_naver_api_news(company_name, ticker, start_date, end_date, headers)
    else:
        return _fetch_rss_news(company_name, ticker, start_date, end_date)


def _fetch_naver_api_news(
    company_name: str,
    ticker: str,
    start_date: str,
    end_date: str,
    headers: dict,
) -> str:
    """Fetch news using Naver Search API."""
    try:
        query = f"{company_name} 주가"
        url = "https://openapi.naver.com/v1/search/news.json"
        params = {
            "query": query,
            "display": 20,
            "sort": "date",
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        items = data.get("items", [])
        if not items:
            return f"No Korean news found for {company_name} ({ticker})"

        # Parse date range
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

        news_str = ""
        count = 0

        for item in items:
            # Parse pubDate
            pub_date_str = item.get("pubDate", "")
            try:
                pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %z")
                pub_date_naive = pub_date.replace(tzinfo=None)
                if not (start_dt <= pub_date_naive <= end_dt):
                    continue
            except (ValueError, TypeError):
                pass

            title = _clean_html(item.get("title", ""))
            description = _clean_html(item.get("description", ""))
            link = item.get("originallink", item.get("link", ""))

            news_str += f"### {title}\n"
            if description:
                news_str += f"{description}\n"
            if link:
                news_str += f"Link: {link}\n"
            news_str += "\n"
            count += 1

        if count == 0:
            return f"No Korean news found for {company_name} ({ticker}) between {start_date} and {end_date}"

        return f"## {company_name} ({ticker}) 한국 뉴스 ({start_date} ~ {end_date}):\n\n{news_str}"

    except Exception as e:
        return f"Error fetching Korean news for {company_name}: {str(e)}"


def _fetch_rss_news(
    company_name: str,
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Fallback: Fetch news using Google News RSS for Korean content."""
    try:
        import urllib.parse

        query = urllib.parse.quote(f"{company_name} 주식")
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"

        response = requests.get(rss_url, timeout=10)
        response.raise_for_status()

        # Parse RSS XML
        import xml.etree.ElementTree as ET

        root = ET.fromstring(response.text)
        items = root.findall(".//item")

        if not items:
            return f"No Korean news found for {company_name} ({ticker})"

        news_str = ""
        count = 0

        for item in items[:15]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            source = item.findtext("source", "")

            news_str += f"### {title}"
            if source:
                news_str += f" (source: {source})"
            news_str += "\n"
            if pub_date:
                news_str += f"Published: {pub_date}\n"
            if link:
                news_str += f"Link: {link}\n"
            news_str += "\n"
            count += 1

        if count == 0:
            return f"No Korean news found for {company_name} ({ticker})"

        return f"## {company_name} ({ticker}) 한국 뉴스 ({start_date} ~ {end_date}):\n\n{news_str}"

    except Exception as e:
        return f"Error fetching Korean news via RSS: {str(e)}"


def get_korean_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 10,
) -> str:
    """Retrieve Korean macro/global economic news.

    Searches for key Korean market topics: BOK base rate, KOSPI outlook,
    USD/KRW exchange rate, Korean economy, etc.
    """
    search_queries = [
        "한국은행 기준금리",
        "코스피 전망",
        "원달러 환율",
        "한국 경제 전망",
        "외국인 투자 한국",
    ]

    headers = _get_naver_headers()

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    all_news = []
    seen_titles = set()

    for query in search_queries:
        try:
            if headers:
                url = "https://openapi.naver.com/v1/search/news.json"
                params = {"query": query, "display": 5, "sort": "date"}
                resp = requests.get(url, headers=headers, params=params, timeout=10)
                resp.raise_for_status()
                items = resp.json().get("items", [])

                for item in items:
                    title = _clean_html(item.get("title", ""))
                    if title and title not in seen_titles:
                        seen_titles.add(title)
                        all_news.append({
                            "title": title,
                            "description": _clean_html(item.get("description", "")),
                            "link": item.get("originallink", item.get("link", "")),
                            "pubDate": item.get("pubDate", ""),
                        })
            else:
                # Fallback to Google News RSS
                import urllib.parse

                encoded_query = urllib.parse.quote(query)
                rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
                resp = requests.get(rss_url, timeout=10)
                if resp.status_code == 200:
                    import xml.etree.ElementTree as ET

                    root = ET.fromstring(resp.text)
                    for item in root.findall(".//item")[:3]:
                        title = item.findtext("title", "")
                        if title and title not in seen_titles:
                            seen_titles.add(title)
                            all_news.append({
                                "title": title,
                                "description": "",
                                "link": item.findtext("link", ""),
                                "pubDate": item.findtext("pubDate", ""),
                            })

        except Exception:
            continue

        if len(all_news) >= limit:
            break

    if not all_news:
        return f"No Korean global/macro news found for {curr_date}"

    news_str = ""
    for article in all_news[:limit]:
        news_str += f"### {article['title']}\n"
        if article["description"]:
            news_str += f"{article['description']}\n"
        if article["pubDate"]:
            news_str += f"Published: {article['pubDate']}\n"
        if article["link"]:
            news_str += f"Link: {article['link']}\n"
        news_str += "\n"

    return f"## 한국 시장/거시경제 뉴스 ({start_date} ~ {curr_date}):\n\n{news_str}"


def _clean_html(text: str) -> str:
    """Remove HTML tags from text."""
    import re

    clean = re.sub(r"<[^>]+>", "", text)
    clean = clean.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return clean.strip()
