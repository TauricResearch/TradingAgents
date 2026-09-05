"""Chinese-platform sentiment fetchers for A-share instruments.

Replaces the US-centric StockTwits / Reddit / Yahoo Finance news sources in
the sentiment analyst. A-share retail discussion and company news are
concentrated on Chinese platforms, so the agent now reads:

  1. Sina Finance stock-news page  -- institutional / news-channel framing
  2. Eastmoney Guba (股吧)          -- retail community posts with read/reply
                                       counts

Both endpoints are public and keyless. Each fetcher degrades gracefully and
returns a plaintext block (or a clear placeholder), so the calling agent
never has to special-case network failures.
"""

from __future__ import annotations

import html
import http.client
import logging
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from parsel import Selector

from .symbol_utils import crypto_base

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "Chrome/124 Safari/537.36"
)
_GUBA_URL = "https://guba.eastmoney.com/list,{code},f.html"
_SINA_NEWS_URL = (
    "https://vip.stock.finance.sina.com.cn/corp/go.php/"
    "vCB_AllNewsStock/symbol/{symbol}.phtml"
)


def _a_share_code(ticker: str) -> str | None:
    """Extract the bare 6-digit A-share code, or None for non-A-shares."""
    if crypto_base(ticker):
        return None
    match = re.search(r"(\d{6})", ticker)
    return match.group(1) if match else None


def _sina_symbol(ticker: str) -> str | None:
    """Map an A-share ticker to Sina's ``sh600036`` / ``sz000021`` form."""
    code = _a_share_code(ticker)
    if not code:
        return None
    upper = ticker.upper()
    if upper.endswith(".SS") or upper.endswith(".SH"):
        prefix = "sh"
    elif upper.endswith(".SZ"):
        prefix = "sz"
    else:
        prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
    return f"{prefix}{code}"


def _clean(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(html.unescape(value).split())


def _fetch_bytes(url: str, referer: str | None = None, timeout: float = 15.0) -> bytes:
    headers = {"User-Agent": _UA}
    if referer:
        headers["Referer"] = referer
    return urlopen(Request(url, headers=headers), timeout=timeout).read()


def fetch_eastmoney_guba(ticker: str, limit: int = 30, timeout: float = 15.0) -> str:
    """Fetch recent Eastmoney Guba (股吧) posts for an A-share ticker.

    Returns a formatted plaintext block with title, author, last-update time,
    read count, and reply count. Falls back to a placeholder on any failure.
    """
    code = _a_share_code(ticker)
    if not code:
        return f"<东方财富股吧不可用于 {ticker}：目前只支持 A 股代码>"

    url = _GUBA_URL.format(code=code)
    try:
        body = _fetch_bytes(url, referer="https://guba.eastmoney.com/", timeout=timeout)
    except (OSError, http.client.HTTPException, HTTPError) as exc:
        logger.warning("Eastmoney Guba fetch failed for %s: %s", ticker, exc)
        return f"<东方财富股吧不可用: {type(exc).__name__}>"

    sel = Selector(text=body.decode("utf-8", errors="replace"))
    rows = sel.css(".listbody .listitem")
    if not rows:
        return f"<东方财富股吧暂无 {code} 的帖子>"

    lines = []
    for row in rows[:limit]:
        title = _clean(row.css(".title a::text").get())
        author = _clean(row.css(".author a::text").get())
        update = _clean(row.css(".update::text").get())
        read = _clean(row.css(".read::text").get())
        reply = _clean(row.css(".reply::text").get())
        lines.append(f"[{update} | 阅读{read} 评论{reply} | 作者:{author}] {title}")

    return (
        f"东方财富股吧 {code} 最近 {len(lines)} 条帖子：\n"
        + "\n".join(lines)
    )


def _parse_sina_news_entries(body: str) -> list[tuple[str, str, str]]:
    """Return ``(date_time, title, url)`` tuples from Sina's news list."""
    block = body
    start = block.find('class="datelist"')
    if start >= 0:
        block = block[start:]
    pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2}(?:\s+|&nbsp;)+(\d{2}:\d{2}))"
        r'(?:\s|&nbsp;)*<a[^>]*?href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>',
        re.S,
    )
    entries = []
    for match in pattern.finditer(block):
        date_time, _time, url, title = match.groups()
        entries.append((_clean(date_time), _clean(title), url.strip()))
    return entries


def fetch_sina_news(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
    timeout: float = 15.0,
) -> str:
    """Fetch recent Sina Finance news for an A-share ticker.

    ``start_date`` / ``end_date`` are optional ``YYYY-MM-DD`` bounds used to
    filter the news list. Returns a formatted plaintext block, or a
    placeholder on failure.
    """
    symbol = _sina_symbol(ticker)
    if not symbol:
        return f"<新浪财经新闻不可用于 {ticker}：目前只支持 A 股代码>"

    url = _SINA_NEWS_URL.format(symbol=symbol)
    try:
        body = _fetch_bytes(url, timeout=timeout)
    except (OSError, http.client.HTTPException, HTTPError) as exc:
        logger.warning("Sina news fetch failed for %s: %s", ticker, exc)
        return f"<新浪财经新闻不可用: {type(exc).__name__}>"

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("gbk", errors="replace")

    entries = _parse_sina_news_entries(text)
    if start_date:
        entries = [e for e in entries if e[0][:10] >= start_date]
    if end_date:
        entries = [e for e in entries if e[0][:10] <= end_date]
    entries = entries[:limit]

    if not entries:
        window = (
            f"（{start_date} 至 {end_date}）" if start_date or end_date else ""
        )
        return f"<新浪财经新闻在{window or '查询窗口'}内暂无 {symbol} 的新闻>"

    lines = [f"[{date_time}] {title}\n    {url}" for date_time, title, url in entries]
    window = (
        f"（{start_date} 至 {end_date}）" if start_date or end_date else ""
    )
    return (
        f"新浪财经新闻 {symbol} 最近 {len(lines)} 条{window}：\n"
        + "\n".join(lines)
    )
