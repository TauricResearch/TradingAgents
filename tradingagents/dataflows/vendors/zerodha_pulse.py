"""Zerodha Pulse news (https://pulse.zerodha.com), crawled with crawl4ai.

Pulse aggregates the last ~24 hours of Indian business news onto one page. Its
search box is client-side: typing three or more characters hides every
``li.box`` whose ``data-search`` text (title + snippet, lower-cased) does not
contain the query. So the vendor drives that box in a real browser, parses the
boxes left visible (level 0), and follows each match to its publisher page
(level 1) for a fuller snippet. It serves the latest articles only, so a
historical window is reported as unavailable, never as empty.

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
from urllib.parse import urldefrag

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.date_window import coverage_gap, in_window
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

PULSE_URL = "https://pulse.zerodha.com/"


def _pub_date(text: str | None) -> datetime | None:
    """A Pulse timestamp ("10:43 PM, 29 Oct 2026", IST) as an aware datetime."""
    with contextlib.suppress(ValueError, TypeError, AttributeError):
        return datetime.strptime(text.strip(), "%I:%M %p, %d %b %Y").replace(tzinfo=IST)
    return None


def _publisher(span) -> str:
    text = clean(span.get_text()) if span else ""
    return text.lstrip("—-– ").strip() or "Unknown"


def _stamp(node) -> datetime | None:
    return _pub_date(node.get("title")) if node else None


def parse_page(html: str) -> list[dict]:
    """Every article on a Pulse page, with whether the live search left it visible.

    A box's "similar stories" are their own articles (title, time, publisher) with
    no snippet. Pulse's search ignores them (it reads only the lead story), so they
    are matched on their own title whatever the box's visibility.
    """
    from bs4 import BeautifulSoup

    articles: list[dict] = []
    for box in BeautifulSoup(html, "html.parser").select("li.box"):
        visible = not box.has_attr("data-pulse-hidden") and not re.search(
            r"display:\s*none", box.get("style") or "")
        anchor = box.select_one("h2.title a")
        if anchor is None:
            continue
        desc = box.select_one(".desc")
        articles.append({
            "title": clean(anchor.get_text()),
            "summary": clean(desc.get_text()) if desc else "",
            "publisher": _publisher(box.select_one(".feed")),
            "link": urldefrag(anchor.get("href") or "")[0],
            "pub_date": _stamp(box.select_one(".date")),
            "search": (box.get("data-search") or "").lower(),
            "visible": visible,
            "similar": False,
        })
        for similar in box.select("ul.similar li"):
            link = similar.select_one("a")
            if link is None:
                continue
            title = clean(link.get_text())
            articles.append({
                "title": title,
                "summary": "",
                "publisher": _publisher(similar.select_one(".feed")),
                "link": urldefrag(link.get("href") or "")[0],
                "pub_date": _stamp(similar.select_one(".date")),
                "search": title.lower(),
                "visible": visible,
                "similar": True,
            })
    return articles


def matches(articles: list[dict], term: str) -> list[dict]:
    """The articles for ``term``: what Pulse's search left visible, plus matching similar stories.

    Applies Pulse's own rule (substring of the lower-cased text) on top, so a page
    whose script failed to filter cannot pass every article off as a match.
    """
    needle = term.lower()
    seen: set[str] = set()
    found = []
    for a in articles:
        key = a["link"] or a["title"]
        if (a["visible"] or a["similar"]) and needle in a["search"] and key not in seen:
            seen.add(key)
            found.append(a)
    return found


async def _crawl(term: str, follow_links: bool, fetch_limit: int) -> tuple[str, dict[str, str]]:
    """Level 0: Pulse with ``term`` typed into its search box. Level 1: each match's page.

    Returns the searched page's HTML and ``{article url: publisher's description}``.
    """
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    # Wait for Pulse's own handlers (bound on load), type into its box, let the 400 ms
    # debounce run, then mark what the search hid: crawl4ai returns the page's HTML
    # without inline ``display: none``, so the hidden boxes are tagged for the parser.
    type_query = f"""
await new Promise(r => {{ if (document.readyState === 'complete') r(); else window.addEventListener('load', r); }});
await new Promise(r => setTimeout(r, 500));
const q = document.querySelector('#q'); q.value = {json.dumps(term)};
if (window.jQuery) {{ window.jQuery(q).trigger('change'); }}
await new Promise(r => setTimeout(r, 800));
document.querySelectorAll('li.box').forEach(b => {{ if (b.style.display === 'none') b.setAttribute('data-pulse-hidden', '1'); }});
"""
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        page = await crawler.arun(
            PULSE_URL,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS, js_code=[type_query], wait_until="load",
                delay_before_return_html=0.5, page_timeout=45000, verbose=False,
            ),
        )
        if not page.success:
            raise VendorUnavailableError(f"Zerodha Pulse crawl failed: {page.error_message}")
        details: dict[str, str] = {}
        if follow_links:
            urls = [a["link"] for a in matches(parse_page(page.html), term) if a["link"]]
            urls = urls[:fetch_limit]
            if urls:
                results = await crawler.arun_many(
                    urls,
                    config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=15000, verbose=False),
                )
                for result in results:
                    meta = (result.metadata or {}) if result.success else {}
                    text = meta.get("og:description") or meta.get("description")
                    if text:
                        details[urldefrag(result.url)[0]] = clean(text)
        return page.html, details


def _run(coro_factory):
    """Run a coroutine to completion from sync code, inside or outside an event loop."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro_factory())).result()


def fetch_matches(term: str) -> tuple[list[dict], list[dict]]:
    """``(matching articles, all articles on the page)`` for one Pulse search."""
    config = get_config()
    html, details = _run(
        lambda: _crawl(term, config.get("pulse_follow_links", True), config.get("pulse_fetch_limit", 5))
    )
    articles = parse_page(html)
    found = matches(articles, term)
    for a in found:
        richer = details.get(a["link"], "")
        if len(richer) > len(a["summary"]):
            a["summary"] = richer
    return found, articles


def get_news_pulse(ticker: str, start_date: str, end_date: str) -> str:
    """News about ``ticker`` from Zerodha Pulse's last 24 hours, in the shared news format.

    Only NSE/BSE tickers (``.NS``, ``.BO``) are searched; any other raises
    ``VendorUnavailableError`` so a configured next vendor serves it.
    The company's name (then its ticker root) is typed into Pulse's search box.
    A window Pulse's day of coverage cannot reach is reported unavailable rather
    than as an absence of news.
    """
    require_indian_ticker("Zerodha Pulse", ticker)
    require_crawl4ai()

    terms = search_terms(ticker)
    if not terms:
        raise VendorUnavailableError(f"Zerodha Pulse has no search term for {ticker}")
    canonical = normalize_symbol(ticker)
    resolved = "" if canonical == ticker else f" (resolved to {canonical})"
    subject = f"news for {ticker}{resolved}"

    article_limit = get_config()["news_article_limit"]
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    page: list[dict] = []
    in_range: list[dict] = []
    for term in terms:
        try:
            found, page = fetch_matches(term)
        except VendorUnavailableError:
            raise
        except Exception as exc:  # crawl4ai / Playwright / network
            raise VendorUnavailableError(f"Zerodha Pulse request failed: {type(exc).__name__}: {exc}") from exc
        in_range = [a for a in found if in_window(a["pub_date"], start_dt, end_dt)]
        if in_range:
            break
    if in_range:
        in_range.sort(key=lambda a: a["pub_date"] or datetime.min.replace(tzinfo=IST), reverse=True)
        return f"## {ticker}{resolved} News, from {start_date} to {end_date}:\n\n{_format_articles(in_range[:article_limit])}"

    # The page is one unbroken newest-first feed, so its oldest article bounds coverage.
    gap = coverage_gap(
        (a["pub_date"] for a in page), start_date, end_date, "Zerodha Pulse news", subject,
    )
    return gap or f"No news found for {ticker}{resolved} between {start_date} and {end_date}"
