import requests
from bs4 import BeautifulSoup
from datetime import datetime
import urllib.parse


def getNewsData(query, start_date, end_date):
    """
    Fetch Google News via RSS feed for a given query and date range.

    Uses Google News RSS which is reliable (no JS rendering or CSS selectors needed).
    Results are filtered to only include articles within the date range.

    query: str - search query (spaces or '+' separated)
    start_date: str - start date in yyyy-mm-dd or mm/dd/yyyy format
    end_date: str - end date in yyyy-mm-dd or mm/dd/yyyy format
    """
    # Normalize dates to datetime objects for filtering
    if "/" in str(start_date):
        start_dt = datetime.strptime(start_date, "%m/%d/%Y")
    else:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")

    if "/" in str(end_date):
        end_dt = datetime.strptime(end_date, "%m/%d/%Y")
    else:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    # Clean up query (replace + with spaces for URL encoding)
    clean_query = query.replace("+", " ")
    encoded_query = urllib.parse.quote(clean_query)

    # Use Google News RSS feed — reliable, no scraping issues
    url = f"https://news.google.com/rss/search?q={encoded_query}+after:{start_dt.strftime('%Y-%m-%d')}+before:{end_dt.strftime('%Y-%m-%d')}&hl=en-IN&gl=IN&ceid=IN:en"

    news_results = []
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return news_results

        soup = BeautifulSoup(resp.content, "xml")
        items = soup.find_all("item")

        for item in items[:20]:  # Limit to 20 articles
            try:
                title = item.find("title").text if item.find("title") else ""
                pub_date_str = item.find("pubDate").text if item.find("pubDate") else ""
                source = item.find("source").text if item.find("source") else ""
                link = item.find("link").text if item.find("link") else ""
                # Description often contains HTML snippet
                desc_tag = item.find("description")
                snippet = ""
                if desc_tag:
                    desc_soup = BeautifulSoup(desc_tag.text, "html.parser")
                    snippet = desc_soup.get_text()[:300]

                # Parse and filter by date
                if pub_date_str:
                    try:
                        pub_dt = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z")
                        if pub_dt.date() < start_dt.date() or pub_dt.date() > end_dt.date():
                            continue
                        date_display = pub_dt.strftime("%Y-%m-%d")
                    except ValueError:
                        date_display = pub_date_str
                else:
                    date_display = ""

                news_results.append({
                    "link": link,
                    "title": title,
                    "snippet": snippet if snippet else title,
                    "date": date_display,
                    "source": source,
                })
            except Exception:
                continue

    except Exception as e:
        print(f"Google News RSS fetch failed: {e}")

    return news_results


def getGlobalNewsData(curr_date, look_back_days=7, limit=10):
    """
    Fetch global/macro news via Google News RSS feed.

    Uses broad financial/market queries to get macroeconomic news.
    """
    if isinstance(curr_date, str):
        end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    else:
        end_dt = curr_date

    from dateutil.relativedelta import relativedelta
    start_dt = end_dt - relativedelta(days=look_back_days)

    queries = [
        "stock market India NSE Nifty",
        "global economy markets finance",
    ]

    all_results = []
    seen_titles = set()

    for query in queries:
        encoded = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}+after:{start_dt.strftime('%Y-%m-%d')}+before:{end_dt.strftime('%Y-%m-%d')}&hl=en-IN&gl=IN&ceid=IN:en"

        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.content, "xml")
            items = soup.find_all("item")

            for item in items:
                try:
                    title = item.find("title").text if item.find("title") else ""
                    if title in seen_titles:
                        continue
                    seen_titles.add(title)

                    pub_date_str = item.find("pubDate").text if item.find("pubDate") else ""
                    source = item.find("source").text if item.find("source") else ""
                    desc_tag = item.find("description")
                    snippet = ""
                    if desc_tag:
                        desc_soup = BeautifulSoup(desc_tag.text, "html.parser")
                        snippet = desc_soup.get_text()[:300]

                    date_display = ""
                    if pub_date_str:
                        try:
                            pub_dt = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z")
                            date_display = pub_dt.strftime("%Y-%m-%d")
                        except ValueError:
                            date_display = pub_date_str

                    all_results.append({
                        "title": title,
                        "snippet": snippet if snippet else title,
                        "date": date_display,
                        "source": source,
                    })
                except Exception:
                    continue

        except Exception:
            continue

    # Sort by date descending and limit
    all_results.sort(key=lambda x: x.get("date", ""), reverse=True)
    return all_results[:limit]
