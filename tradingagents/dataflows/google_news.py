"""
Google News RSS Provider for TradingAgents.
Requires optional dependencies: pip install "tradingagents[news]"
"""

import asyncio
import logging
import re
import os
import urllib.parse
import xml.etree.ElementTree as ET
from pydantic import BaseModel, HttpUrl, Field

try:
    import aiohttp
    from bs4 import BeautifulSoup
    from readability import Document
    from googlenewsdecoder import gnewsdecoder
except ImportError:
    raise ImportError(
        "Missing required dependencies for google_news. "
        "Please install them via: pip install 'tradingagents[news]'"
    )

logger = logging.getLogger(__name__)

# Jina free tier: Concurrency 5. Never exceed this.
JINA_CONCURRENCY_LIMIT = int(os.environ.get("JINA_CONCURRENCY_LIMIT", 5))

# Hard character cap — prevents LLM OOM on 4GB VRAM
MAX_CHARS = 6000


class NewsArticle(BaseModel):
    title: str
    url: HttpUrl
    source: str = Field(default="Google News RSS")
    published_date: str | None = None
    summary: str
    full_text: str
    scraped: bool


async def unroll_google_link(google_url: str) -> str:
    """
    Decrypts the Google News redirect URL.
    Runs in a thread to avoid blocking the asyncio event loop.
    """
    def _decode():
        try:
            logger.debug(f"Decrypting Google Link: {google_url}")
            result = gnewsdecoder(google_url)
            if result.get("status"):
                real_url = result["decoded_url"]
                logger.debug(f"Successfully decrypted: {real_url}")
                return real_url
            else:
                logger.debug(f"Decryption failed, falling back to original: {result.get('message')}")
                return google_url
        except Exception as e:
            logger.debug(f"Decoder exception: {e}")
            return google_url

    return await asyncio.to_thread(_decode)


def clean_and_truncate(text: str, max_chars: int = MAX_CHARS) -> str:
    """
    Standardized text cleaner for all scraper output.
    Collapses whitespace, strips garbage, and enforces a hard character cap
    to prevent LLM OOM crashes on low-VRAM GPUs.
    """
    if not text:
        return ""
    clean_text = re.sub(r'\s+', ' ', text).strip()
    if len(clean_text) > max_chars:
        # Keep head and tail — job title is often at top, location at bottom
        half = max_chars // 2
        return clean_text[:half] + "\n\n...[TRUNCATED]...\n\n" + clean_text[-half:]
    return clean_text


async def _jina_scrape(session: aiohttp.ClientSession, url: str) -> str | None:
    """
    Jina Reader Free Tier — converts any URL to clean markdown.
    No API key required. Rate-limited but free.
    """
    jina_url = f"https://r.jina.ai/{url}"
    try:
        async with session.get(jina_url, headers={"Accept": "text/plain"}, timeout=15) as res:
            if res.status == 200:
                text = await res.text(encoding='utf-8', errors='replace')
                if len(text.strip()) > 100:
                    logger.debug(f"Jina Reader success: {url}")
                    return clean_and_truncate(text)
    except Exception as e:
        logger.debug(f"Jina Reader failed for {url}: {e}")
    return None


async def _readability_scrape(session: aiohttp.ClientSession, url: str) -> str | None:
    """
    Local readability-lxml fallback — the same algorithm Firefox Reader View uses.
    Strips sidebars, navs, footers, and ads. Returns only the main article content.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        async with session.get(url, headers=headers, timeout=15) as response:
            if response.status != 200:
                logger.debug(f"Readability fetch failed ({response.status}): {url}")
                return None

            html = await response.text(encoding='utf-8', errors='replace')
            doc = Document(html)
            summary_html = doc.summary()

            # Convert the cleaned HTML summary to plain text
            soup = BeautifulSoup(summary_html, "lxml")
            
            # Extra safety: strip any remaining garbage tags
            for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
                element.decompose()

            text = soup.get_text(separator=' ', strip=True)

            if len(text.strip()) > 100:
                logger.debug(f"Readability success: {url}")
                return clean_and_truncate(text)

    except Exception as e:
        logger.debug(f"Readability failed for {url}: {e}")

    return None


async def _deep_scrape_article(
    session: aiohttp.ClientSession, 
    semaphore: asyncio.Semaphore, 
    item_data: dict
) -> NewsArticle:
    """
    Worker function: unroll Google redirect + scrape article.
    """
    link = item_data["link"]
    title = item_data["title"]
    description = item_data["description"]
    pub_date = item_data["pub_date"]

    skip_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.mp4', '.pdf')
    
    real_url = await unroll_google_link(link)
    is_article = not any(real_url.lower().split('?')[0].endswith(ext) for ext in skip_extensions)

    full_body = None
    scraped = False

    if is_article:
        async with semaphore:
            full_body = await _jina_scrape(session, real_url)
            if not full_body:
                full_body = await _readability_scrape(session, real_url)

    if full_body:
        scraped = True
        full_text = (
            f"Headline: {title}\n"
            f"Published: {pub_date or 'Unknown'}\n"
            f"Full Article:\n{full_body}"
        )
        logger.info(f"Deep-scraped: {title[:60]}... ({len(full_body)} chars)")
    else:
        full_text = f"Headline: {title}\nSummary: {description}"
        logger.debug(f"RSS-only (deep scrape failed or skipped): {title[:60]}...")

    return NewsArticle(
        title=title,
        url=real_url,
        published_date=pub_date,
        summary=description,
        full_text=full_text,
        scraped=scraped
    )


async def get_google_news(query: str, time_range: str = "7d", limit: int = 15) -> list[NewsArticle]:
    """
    Fetches Google News RSS for a given query and deep-scrapes the articles concurrently.
    
    Args:
        query: Search query string (e.g., "NVIDIA stock earnings news").
        time_range: Time range for news (default "7d").
        limit: Max number of articles to retrieve (default 15).
        
    Returns:
        List of NewsArticle objects with full-text when available.
    """
    safe_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={safe_query}+when:{time_range}&hl=en-US&gl=US&ceid=US:en"
    
    pending = []
    seen_urls = set()

    async with aiohttp.ClientSession() as session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            async with session.get(url, headers=headers, timeout=15) as res:
                if res.status != 200:
                    logger.warning(f"Google News RSS blocked with status: {res.status}")
                    return []
                
                xml_data = await res.text(encoding='utf-8', errors='replace')
                root = ET.fromstring(xml_data)

                for item in root.findall('.//item')[:limit]:
                    link = item.find('link').text if item.find('link') is not None else ""
                    if not link or link in seen_urls:
                        continue

                    title = item.find('title').text if item.find('title') is not None else ""
                    description = item.find('description').text if item.find('description') is not None else ""
                    pub_date = item.find('pubDate').text if item.find('pubDate') is not None else None

                    seen_urls.add(link)
                    pending.append({
                        "link": link,
                        "title": title,
                        "description": description,
                        "pub_date": pub_date,
                    })

        except Exception as e:
            logger.error(f"Error parsing Google News XML: {e}")
            return []

        if not pending:
            logger.info("No articles found in Google News RSS.")
            return []

        logger.info(f"Found {len(pending)} articles. Deep-scraping concurrently (limit={JINA_CONCURRENCY_LIMIT})...")

        semaphore = asyncio.Semaphore(JINA_CONCURRENCY_LIMIT)
        tasks = [_deep_scrape_article(session, semaphore, item) for item in pending]
        
        articles = await asyncio.gather(*tasks, return_exceptions=True)
        
        results = []
        for res in articles:
            if isinstance(res, Exception):
                logger.warning(f"Error during deep scrape: {res}")
            elif isinstance(res, NewsArticle):
                results.append(res)
                
        logger.info(f"Completed deep scraping. Total articles: {len(results)}")
        return results
