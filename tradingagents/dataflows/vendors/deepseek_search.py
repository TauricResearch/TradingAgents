"""Company and global news from DeepSeek Search, bounded to the run's window.

Yahoo serves only recent articles, so a past-dated run reads no company news. DeepSeek Search
(https://api-docs.deepseek.com/guides/search/) takes ``after:`` and ``before:`` operators and dates
each result, so both news tools can serve any window. Search results carry later information in
three ways, and each is guarded here:

- a result's date can read a day early, so on a past date the window ends the day before the run;
- a site's rolling page ("news today", a topic or forecast page) keeps its first date while its
  text is rewritten daily, so those pages are dropped by URL and title;
- a summary is today's version of the page, so a result whose title or summary names a date after
  the window, up to today, is dropped. A scheduled date still ahead is kept.

Reads ``DEEPSEEK_API_KEY``. DeepSeek bills $0.75 per 1,000 successful searches.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta

import requests

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.date_window import is_historical
from tradingagents.dataflows.errors import VendorNotConfiguredError, VendorUnavailableError

SEARCH_URL = "https://api.deepseek.com/v1/tools/search"
ROLLING = re.compile(
    r"news today|latest news|live updates|stock forecast|forecast & analyst"
    r"|/topic/|/tag/|/quote/|/symbol/|/forecast",
    re.I,
)
_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_DATES = [
    (re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b"), lambda y, m, d: (y, m, d)),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})\b"), lambda m, d, y: (y, m, d)),
    (re.compile(rf"\b{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(20\d\d))?", re.I),
     lambda mon, d, y: (y, mon, d)),
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MONTH}(?:\s+(20\d\d))?", re.I),
     lambda d, mon, y: (y, mon, d)),
]


def mentioned_dates(text: str, year: int) -> list[date]:
    """Calendar dates written in ``text``; a date written without a year takes ``year``."""
    found = []
    for pattern, order in _DATES:
        for groups in pattern.findall(text):
            y, m, d = order(*groups)
            if isinstance(m, str) and not m.isdigit():
                m = "janfebmaraprmayjunjulaugsepoctnovdec".index(m[:3].lower()) // 3 + 1
            y = int(y) if y else year
            y = y + 2000 if y < 100 else y
            try:
                found.append(date(y, int(m), int(d)))
            except ValueError:
                continue
    return found


def _search(query: str, count: int) -> list[dict]:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise VendorNotConfiguredError("DeepSeek Search needs DEEPSEEK_API_KEY")
    try:
        response = requests.post(
            SEARCH_URL,
            json={"query": query[:128], "count": max(1, min(count, 50))},
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"DeepSeek Search failed: {type(exc).__name__}") from None
    return response.json().get("results") or []


def _published(result: dict) -> date | None:
    try:
        return datetime.fromisoformat((result.get("date") or "").replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _last_day(end_date: str) -> date:
    """Last publication day a run may read: the day before a past run date, else today."""
    end = date.fromisoformat(end_date)
    return end - timedelta(days=1) if is_historical(end_date) else end


def _in_window(results: list[dict], start: date, last: date, seen: set[str]) -> list[dict]:
    kept = []
    for r in results:
        day, url, title = _published(r), r.get("url") or "", r.get("title") or ""
        if day is None or not start <= day <= last or url in seen:
            continue
        if ROLLING.search(url) or ROLLING.search(title):
            continue
        text = f"{title} {r.get('summary') or ''}"
        if any(last < d <= date.today() for d in mentioned_dates(text, last.year)):
            continue
        seen.add(url)
        kept.append(r)
    return kept


def _summary(result: dict, limit: int = 600) -> str:
    """Article text without page furniture: headings, quote and table rows, ellipsis lines."""
    lines = []
    for line in (result.get("summary") or result.get("snippet") or "").splitlines():
        line = re.sub(r"^\s*#+\s*", "", line).strip()
        if line and line != "..." and "|" not in line:
            lines.append(line)
    text = " ".join(lines)
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " ..."


def _format(results: list[dict]) -> str:
    out = ""
    for r in results:
        title = (r.get("title") or "No title").split(" - Skip to")[0]
        title = re.sub(r"\s+-\s+[0-9a-f]{12,}\S*$", "", title).strip()[:160]  # tracking ids
        out += f"### {title} (source: {r.get('site_name') or 'unknown'}, {_published(r)})\n"
        summary = _summary(r)
        if summary:
            out += f"{summary}\n"
        if r.get("url"):
            out += f"Link: {r['url']}\n"
        out += "\n"
    return out


def _collect(queries: list[str], start: date, last: date, limit: int) -> list[dict]:
    window = f"lang:en after:{start.isoformat()} before:{(last + timedelta(days=1)).isoformat()}"
    kept: list[dict] = []
    seen: set[str] = set()
    for query in queries:
        kept += _in_window(_search(f"{query} {window}", limit), start, last, seen)
        if len(kept) >= limit:
            break
    return kept[:limit]


def get_news_deepseek(ticker: str, start_date: str, end_date: str) -> str:
    """News about ``ticker`` published in the window, from DeepSeek Search."""
    start, last = date.fromisoformat(start_date), _last_day(end_date)
    queries = [f"{ticker} stock news", f"{ticker} shares analysts earnings"]
    kept = _collect(queries, start, last, get_config()["news_article_limit"])
    if not kept:
        return f"No news found for {ticker} between {start_date} and {last}"
    return f"## {ticker} News, from {start_date} to {last}:\n\n{_format(kept)}"


def get_global_news_deepseek(
    as_of_date: str, look_back_days: int | None = None, limit: int | None = None
) -> str:
    """Macro and market news from DeepSeek Search over the configured global queries."""
    config = get_config()
    look_back_days = look_back_days or config["global_news_lookback_days"]
    limit = limit or config["global_news_article_limit"]
    last = _last_day(as_of_date)
    start = date.fromisoformat(as_of_date) - timedelta(days=look_back_days)
    kept = _collect(config["global_news_queries"], start, last, limit)
    if not kept:
        return f"No global news found between {start} and {last}"
    return f"## Global Market News, from {start} to {last}:\n\n{_format(kept)}"
