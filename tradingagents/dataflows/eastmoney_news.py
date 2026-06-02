"""East Money (东方财富) per-stock news fetcher for Chinese A-shares.

Yahoo Finance and Alpha Vantage are English-centric and return little or no
news for Shanghai/Shenzhen-listed tickers (e.g. ``600519.SS``). East Money's
public search endpoint indexes Chinese-language financial news keyed by the
six-digit stock code, requires no API key, OAuth, or registration, and returns
structured JSON (title, publish date, summary, media outlet, link).

The function mirrors :func:`get_news_yfinance`: same signature, same date
filtering, and the same plaintext block shape so the News Analyst prompt is
identical regardless of which vendor served the request. Like every other
fetcher here it degrades gracefully — any network or parse failure returns a
string rather than raising, so the run is never crashed by a flaky source.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import get_config

logger = logging.getLogger(__name__)

# Public East Money site-search endpoint. ``cmsArticleWebOld`` is the news
# article index; the response is JSONP wrapped in ``<cb>( ... )``.
_API = "https://search-api-web.eastmoney.com/search/jsonp"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"

# A-share exchange suffixes (Yahoo convention): Shanghai / Shenzhen.
_ASHARE_SUFFIXES = (".SS", ".SZ")

_TAG_RE = re.compile(r"</?em>")
_JSONP_RE = re.compile(r"^[^(]*\((.*)\)\s*;?\s*$", re.DOTALL)


def is_ashare(ticker: str) -> bool:
    """True for Shanghai/Shenzhen-listed tickers (``600519.SS``, ``000858.SZ``)."""
    return ticker.upper().endswith(_ASHARE_SUFFIXES)


def _strip_tags(text: str) -> str:
    """Remove the ``<em>`` highlight tags East Money wraps around query matches."""
    return _TAG_RE.sub("", text or "").strip()


def _build_url(code: str, page_size: int) -> str:
    param = {
        "uid": "",
        "keyword": code,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "time",
                "pageIndex": 1,
                "pageSize": page_size,
                "preTag": "",
                "postTag": "",
            }
        },
    }
    return f"{_API}?cb=cb&param={quote(json.dumps(param, ensure_ascii=False))}"


def get_news_eastmoney(ticker: str, start_date: str, end_date: str) -> str:
    """Retrieve Chinese news for an A-share ``ticker`` via East Money.

    Args:
        ticker: A-share ticker with exchange suffix, e.g. ``600519.SS``.
        start_date: Start date in ``yyyy-mm-dd`` format (inclusive).
        end_date: End date in ``yyyy-mm-dd`` format (inclusive).

    Returns:
        A formatted plaintext block of news, or an explanatory string when the
        ticker is not an A-share, no news falls in the window, or the source is
        unreachable. Never raises.
    """
    if not is_ashare(ticker):
        # Defensive: this vendor only covers A-shares. Returning a plain string
        # lets the router fall through to an English-centric vendor.
        return f"East Money only covers A-shares; {ticker} is out of scope."

    code = ticker.split(".")[0]
    article_limit = get_config()["news_article_limit"]
    url = _build_url(code, article_limit)
    # The endpoint replies with JSONP (text/javascript); requesting
    # application/json gets a 406, so accept any content type.
    req = Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})

    try:
        with urlopen(req, timeout=10.0) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        match = _JSONP_RE.match(raw.strip())
        data = json.loads(match.group(1) if match else raw)
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, UnicodeError) as exc:
        logger.warning("East Money news fetch failed for %s: %s", ticker, exc)
        return f"<east money news unavailable: {type(exc).__name__}>"

    articles = (data.get("result") or {}).get("cmsArticleWebOld") or []
    if not articles:
        return f"No news found for {ticker}"

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)

    news_str = ""
    kept = 0
    for art in articles:
        date_raw = (art.get("date") or "").strip()
        pub_dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                pub_dt = datetime.strptime(date_raw, fmt)
                break
            except ValueError:
                continue
        if pub_dt and not (start_dt <= pub_dt <= end_dt):
            continue

        title = _strip_tags(art.get("title", ""))
        if not title:
            continue
        media = _strip_tags(art.get("mediaName", "")) or "东方财富"
        summary = _strip_tags(art.get("content", ""))
        link = (art.get("url") or "").strip()

        news_str += f"### {title} (source: {media}, {date_raw})\n"
        if summary:
            news_str += f"{summary}\n"
        if link:
            news_str += f"Link: {link}\n"
        news_str += "\n"
        kept += 1

    if kept == 0:
        return f"No news found for {ticker} between {start_date} and {end_date}"

    return f"## {ticker} News (East Money / 东方财富), from {start_date} to {end_date}:\n\n{news_str}"
