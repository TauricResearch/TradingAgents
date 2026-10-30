"""NDTV Profit news, research reports and peer comparison (https://www.ndtvprofit.com),
crawled with crawl4ai.

The vendor types the company name into the site's search box and reads the results
page (stories), reads the research-reports topic page for the company's reports,
and opens the company's stock page to read its "Peer Comparison" readout: the stock's
move in the latest session against NIFTY 50 (the widget's period selector redraws the
chart but leaves that readout unchanged, so no longer period is reported), with the
sector and cap class. Results come back in the shared news format; the peer comparison
follows. It is a present-day snapshot, so a run dated in the past gets a notice instead.

crawl4ai is an optional dependency: ``pip install "tradingagents[crawl4ai]"``.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import json
import logging
import re
from datetime import datetime

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.date_window import coverage_gap, in_window, is_historical
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.india import (
    IST,
    clean,
    require_crawl4ai,
    require_indian_ticker,
    search_terms,
)
from tradingagents.dataflows.vendors.yahoo.news import _format_articles

logger = logging.getLogger(__name__)

SITE = "https://www.ndtvprofit.com"
MARKETS_URL = f"{SITE}/markets?src=topnav"
REPORTS_URL = f"{SITE}/topic/research-reports"
_STORY_SOURCE = "NDTV Profit"
_REPORT_SOURCE = "NDTV Profit, research report"
# "Oct 29, 2026 22:29 pm IST": the clock is 24-hour whatever the am/pm says.
_STAMP = re.compile(r"([A-Z][a-z]{2} \d{1,2}, \d{4} \d{1,2}:\d{2})")
_READOUT = re.compile(
    r"^(?P<a>.+?)\s+(?P<ac>[+-]?[\d,]*\.?\d+)\s+\((?P<ap>[+-]?[\d.]+)%\)"
    r"\s+(?P<b>.+?)\s+(?P<bc>[+-]?[\d,]*\.?\d+)\s+\((?P<bp>[+-]?[\d.]+)%\)$"
)


def _pub_date(text: str | None) -> datetime | None:
    found = _STAMP.search(text or "")
    if not found:
        return None
    with contextlib.suppress(ValueError):
        return datetime.strptime(found.group(1), "%b %d, %Y %H:%M").replace(tzinfo=IST)
    return None


def parse_articles(html: str) -> list[dict]:
    """The article cards on a search-results or topic page (class names are hashed, so
    elements are found by the stable part of the name)."""
    from bs4 import BeautifulSoup

    articles = []
    for card in BeautifulSoup(html, "html.parser").select("li[class*=articleItem]"):
        link = card.select_one("a[class*=articleTitle]")
        if link is None or not link.get("href"):
            continue
        excerpt, stamp = card.select_one("[class*=articleExcerpt]"), card.select_one("[class*=metaText]")
        articles.append({
            "title": clean(link.get_text()),
            "summary": clean(excerpt.get_text()) if excerpt else "",
            "link": link["href"],
            "pub_date": _pub_date(stamp.get_text() if stamp else None),
            "publisher": _STORY_SOURCE,
        })
    return articles


def parse_peer_readout(text: str) -> dict | None:
    """``"Stock +9.40 (0.81%) NIFTY 50 +237.90 (1.05%)"`` as a row, or None if unreadable."""
    found = _READOUT.match(clean(text))
    return found.groupdict() if found else None


def format_peer_comparison(row: dict | None, sector: str, as_of: str) -> str:
    if not row:
        return ""
    out = f"## Peer comparison, {row['a']} vs {row['b']} (NDTV Profit, latest session as of {as_of}):\n\n"
    if sector:
        out += f"Sector / cap class: {sector}\n"
    out += (f"{row['a']}: {row['ac']} ({row['ap']}%)\n"
            f"{row['b']}: {row['bc']} ({row['bp']}%)\n\n")
    return out


def withheld_peer_comparison(as_of: str) -> str:
    return (
        f"## Peer comparison (NDTV Profit)\n\nWithheld for {as_of}: the site serves only "
        f"present-day performance figures with no history, so showing them would put "
        f"post-{as_of} information into the analysis.\n\n"
    )


async def _crawl(term: str, symbol: str | None) -> dict:
    """Search the site for ``term``, then read the reports page and, when asked, the stock page.

    ``symbol`` is the NSE symbol for the stock page, or None to skip it.
    """
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    search_js = f"""
await new Promise(r => {{ if (document.readyState === 'complete') r(); else window.addEventListener('load', r); }});
await new Promise(r => setTimeout(r, 2000));
const box = document.querySelector('input[placeholder="Search NDTV Profit"]');
box.focus();
Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(box, {json.dumps(term)});
box.dispatchEvent(new Event('input', {{bubbles: true}}));
await new Promise(r => setTimeout(r, 1500));
for (const t of ['keydown', 'keypress', 'keyup'])
    box.dispatchEvent(new KeyboardEvent(t, {{key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true}}));
await new Promise(r => setTimeout(r, 3500));
"""
    peers_js = r"""
await new Promise(r => { if (document.readyState === 'complete') r(); else window.addEventListener('load', r); });
await new Promise(r => setTimeout(r, 3500));
const card = [...document.querySelectorAll('h3')].find(h => h.textContent.trim() === 'Peer Comparison')?.closest('div[class]');
const el = card && card.querySelector('[class*=legend], [class*=Legend], [class*=summary], [class*=stats]');
const pre = document.createElement('pre'); pre.id = 'ndtv-peers';
pre.textContent = el ? el.innerText.replace(/\s+/g, ' ').trim() : '';
document.body.appendChild(pre);
"""
    result: dict = {"search": "", "reports": "", "peers": "", "sector": ""}
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        def config(js=None, delay=1.0):
            return CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS, js_code=[js] if js else None, wait_until="load",
                delay_before_return_html=delay, page_timeout=45000, verbose=False,
            )

        page = await crawler.arun(MARKETS_URL, config=config(search_js))
        if not page.success:
            raise VendorUnavailableError(f"NDTV Profit search failed: {page.error_message}")
        result["search"] = page.html
        reports = await crawler.arun(REPORTS_URL, config=config(delay=2.0))
        if reports.success:
            result["reports"] = reports.html
        if symbol:
            from bs4 import BeautifulSoup

            stock = await crawler.arun(f"{SITE}/stocks/x-share-price-{symbol}", config=config(peers_js))
            soup = BeautifulSoup(stock.html, "html.parser") if stock.success else None
            node = soup.select_one("#ndtv-peers") if soup else None
            result["peers"] = node.get_text() if node else ""
            title = soup.select_one("h1") if soup else None
            tag = title.find_previous(string=re.compile("•")) if title else None
            result["sector"] = clean(tag) if tag else ""
    return result


def _run(coro_factory):
    """Run a coroutine to completion from sync code, inside or outside an event loop."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro_factory())).result()


def _stock_symbol(ticker: str) -> str | None:
    """The NSE symbol the stock page is keyed by, or None for a numeric BSE scrip code."""
    root = normalize_symbol(ticker).split(".")[0]
    return None if root.isdigit() else root


def fetch(term: str, ticker: str, want_peers: bool) -> tuple[list[dict], list[dict], dict | None, str]:
    """``(search stories, matching research reports, peer row, sector)`` for one search term."""
    crawled = _run(lambda: _crawl(term, _stock_symbol(ticker) if want_peers else None))
    topic = parse_articles(crawled["reports"])
    report_links = {a["link"] for a in topic}
    # A search hit that the research-reports page also lists is a report, not a story.
    stories = [
        {**a, "publisher": _REPORT_SOURCE} if a["link"] in report_links else a
        for a in parse_articles(crawled["search"])
    ]
    needle = term.lower()
    reports = [
        {**a, "publisher": _REPORT_SOURCE} for a in topic
        if needle in f"{a['title']} {a['summary']}".lower()
    ]
    return stories, reports, parse_peer_readout(crawled["peers"]), crawled["sector"]


def get_news_ndtv_profit(ticker: str, start_date: str, end_date: str) -> str:
    """Stories and research reports about ``ticker`` from NDTV Profit, plus its peer comparison.

    Only NSE/BSE tickers (``.NS``, ``.BO``) are searched; any other raises
    ``VendorUnavailableError`` so a configured next vendor serves it. The company's name
    (then its ticker root) is typed into the site's search box. Articles are returned in
    the shared news format, newest first, reports marked in their source; the peer
    comparison follows unless the run is dated in the past.
    """
    require_indian_ticker("NDTV Profit", ticker)
    require_crawl4ai()
    terms = search_terms(ticker)
    if not terms:
        raise VendorUnavailableError(f"NDTV Profit has no search term for {ticker}")
    canonical = normalize_symbol(ticker)
    resolved = "" if canonical == ticker else f" (resolved to {canonical})"
    subject = f"news for {ticker}{resolved}"

    config = get_config()
    article_limit = config["news_article_limit"]
    live = not is_historical(end_date)
    want_peers = live and config.get("ndtv_peer_comparison", True)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    stories: list[dict] = []
    in_range: list[dict] = []
    peers: dict | None = None
    sector = ""
    for term in terms:
        try:
            stories, reports, found_peers, found_sector = fetch(term, ticker, want_peers and not peers)
        except VendorUnavailableError:
            raise
        except Exception as exc:  # crawl4ai / Playwright / network
            raise VendorUnavailableError(f"NDTV Profit request failed: {type(exc).__name__}: {exc}") from exc
        peers, sector = peers or found_peers, sector or found_sector
        seen: set[str] = set()
        for a in [*stories, *reports]:
            if a["link"] not in seen and in_window(a["pub_date"], start_dt, end_dt):
                seen.add(a["link"])
                in_range.append(a)
        if in_range:
            break

    if in_range:
        in_range.sort(key=lambda a: a["pub_date"] or datetime.min.replace(tzinfo=IST), reverse=True)
        body = (f"## {ticker}{resolved} News, from {start_date} to {end_date}:\n\n"
                f"{_format_articles(in_range[:article_limit])}")
    else:
        # Search results come newest first, so the oldest on the page bounds coverage; a
        # page that is not in date order proves no coverage, leaving only the present.
        dates = [a["pub_date"] for a in stories if a["pub_date"]]
        ordered = all(x >= y for x, y in zip(dates, dates[1:], strict=False))
        gap = coverage_gap(dates if ordered else (), start_date, end_date, "NDTV Profit news", subject)
        body = gap or f"No news found for {ticker}{resolved} between {start_date} and {end_date}"
        body += "\n\n"

    if not live:
        return body + withheld_peer_comparison(end_date)
    if not want_peers:
        return body
    return body + format_peer_comparison(peers, sector, datetime.now(IST).strftime("%Y-%m-%d"))
