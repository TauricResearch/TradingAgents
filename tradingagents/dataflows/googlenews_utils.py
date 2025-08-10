import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
import random
import logging
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_result,
)


def is_rate_limited(response):
    """Check if the response indicates we should back off (rate-limited or temporarily unavailable)."""
    return response.status_code in (429, 403, 503)


def _add_jitter(retry_state):
    # Add small random jitter before each retry to avoid detection patterns
    time.sleep(random.uniform(1, 3))


@retry(
    retry=(retry_if_result(is_rate_limited)),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    before_sleep=_add_jitter,
    stop=stop_after_attempt(5),
)
def make_request(url, headers):
    """Make a request with retry logic for rate limiting"""
    # The retry decorator already applies exponential backoff with jitter
    response = requests.get(url, headers=headers, timeout=(5, 20))
    return response


def getNewsData(query, start_date, end_date):
    """
    Scrape Google News search results for a given query and date range.
    query: str - search query
    start_date: str - start date in the format yyyy-mm-dd or mm/dd/yyyy
    end_date: str - end date in the format yyyy-mm-dd or mm/dd/yyyy
    """
    if "-" in start_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
        start_date = start_date.strftime("%m/%d/%Y")
    if "-" in end_date:
        end_date = datetime.strptime(end_date, "%Y-%m-%d")
        end_date = end_date.strftime("%m/%d/%Y")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/101.0.4951.54 Safari/537.36"
        )
    }

    news_results = []
    page = 0
    while True:
        offset = page * 10
        encoded_query = quote_plus(query)
        url = (
            f"https://www.google.com/search?q={encoded_query}"
            f"&tbs=cdr:1,cd_min:{start_date},cd_max:{end_date}"
            f"&tbm=nws&start={offset}"
        )

        try:
            response = make_request(url, headers)
            soup = BeautifulSoup(response.content, "html.parser")
            results_on_page = soup.select("div.SoaBEf")

            if not results_on_page:
                break  # No more results found

            for el in results_on_page:
                try:
                    link_tag = el.find("a")
                    title_el = el.select_one("div.MBeuO")
                    if not link_tag or not title_el:
                        # Skip if required elements are missing
                        continue
                    link = link_tag.get("href")
                    title = title_el.get_text(strip=True)
                    snippet_el = el.select_one(".GI74Re")
                    date_el = el.select_one(".LfVVr")
                    source_el = el.select_one(".NUnG9d span")
                    news_results.append(
                        {
                            "link": link,
                            "title": title,
                            "snippet": (
                                snippet_el.get_text(strip=True) if snippet_el else ""
                            ),
                            "date": date_el.get_text(strip=True) if date_el else "",
                            "source": (
                                source_el.get_text(strip=True) if source_el else ""
                            ),
                        }
                    )
                except Exception as e:
                    logger.warning("Error processing result: %s", e)
                    # If one of the fields is not found, skip this result
                    continue

            # Update the progress bar with the current count of results scraped

            # Check for the "Next" link (pagination)
            next_link = soup.find("a", id="pnnext")
            if not next_link:
                break

            page += 1

        except Exception as e:
            logger.error("Failed after multiple retries: %s", e)
            break

    return news_results
