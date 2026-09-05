"""Sina Finance news vendor for ticker and global news tools."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import requests

from .china_sentiment import fetch_sina_news

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "Chrome/124 Safari/537.36"
)
_ROLL_URL = "https://feed.mix.sina.com.cn/api/roll/get"


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """Return ticker-specific Chinese news from Sina Finance."""
    return fetch_sina_news(ticker, start_date=start_date, end_date=end_date)


def get_global_news(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """Return recent Chinese finance headlines from Sina's roll feed."""
    days = look_back_days or 7
    count = limit or 20
    try:
        resp = requests.get(
            _ROLL_URL,
            params={"pageid": "153", "lid": "2516", "num": count, "page": "1"},
            headers={"User-Agent": _UA, "Referer": "https://finance.sina.com.cn/"},
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Sina global news fetch failed: %s", exc)
        return f"<新浪全球新闻不可用: {type(exc).__name__}>"

    rows = ((payload.get("result") or {}).get("data")) or []
    if not rows:
        return "<新浪全球新闻暂无内容>"

    cutoff = datetime.now() - timedelta(days=days)
    lines = []
    for item in rows:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        ctime = item.get("ctime")
        try:
            published = datetime.fromtimestamp(int(ctime))
        except (TypeError, ValueError):
            published = None
        if published and published < cutoff:
            continue
        date_str = published.strftime("%Y-%m-%d %H:%M") if published else "?"
        lines.append(f"[{date_str}] {title}\n    {url}")
        if len(lines) >= count:
            break

    if not lines:
        return f"<新浪全球新闻在近 {days} 天内暂无内容>"
    return f"## 新浪财经全球新闻（近 {days} 天，{len(lines)} 条）：\n\n" + "\n".join(lines)
