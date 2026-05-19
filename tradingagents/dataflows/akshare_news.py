"""Akshare-based news fetchers for China A-share market.

Provides stock-specific and global/market news using akshare's news APIs,
with the same function signatures as the yfinance implementations.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Optional

import pandas as pd

from .a_share_common import normalize_ashare_symbol, to_plain_code
from .akshare_stock import _ak_retry
from .config import get_config


# ── Stock-specific news ─────────────────────────────────────────────────

def get_news(
    ticker: Annotated[str, "ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve news for a specific A-share stock via akshare.

    Uses East Money's individual stock news feed.
    """
    import akshare as ak

    normalized = normalize_ashare_symbol(ticker)
    code = to_plain_code(ticker)

    try:
        df = _ak_retry(
            ak.stock_news_em,
            symbol=code,
        )
    except Exception as exc:
        return (
            f"## {normalized} News, from {start_date} to {end_date}\n\n"
            f"Error fetching news: {type(exc).__name__}: {str(exc)[:200]}"
        )

    if df is None or df.empty:
        return f"No news found for {normalized}"

    # Parse dates and filter by range
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    # akshare news columns: 关键词, 新闻标题, 新闻内容, 发布时间, 文章来源, 新闻链接
    if "发布时间" in df.columns:
        df["发布时间"] = pd.to_datetime(df["发布时间"], errors="coerce")
        df = df[df["发布时间"].notna()]
        df = df[(df["发布时间"] >= start_dt) & (df["发布时间"] <= end_dt + timedelta(days=1))]
        df = df.sort_values("发布时间", ascending=False)

    config = get_config()
    limit = config.get("news_article_limit", 20)
    df = df.head(limit)

    if df.empty:
        return f"No news found for {normalized} between {start_date} and {end_date}"

    news_str = ""
    for _, row in df.iterrows():
        title = str(row.get("新闻标题", "")).strip()
        source = str(row.get("文章来源", "")).strip()
        content = str(row.get("新闻内容", "")).strip()
        link = str(row.get("新闻链接", "")).strip()
        pub_time = row.get("发布时间")
        pub_str = pub_time.strftime("%Y-%m-%d %H:%M") if pd.notna(pub_time) else ""

        if title:
            news_str += f"### {title}"
            if source and source != "nan":
                news_str += f" (source: {source})"
            news_str += "\n"
            if pub_str:
                news_str += f"Published: {pub_str}\n"
            if content and content != "nan":
                # Truncate long content
                if len(content) > 300:
                    content = content[:300] + "..."
                news_str += f"{content}\n"
            if link and link != "nan":
                news_str += f"Link: {link}\n"
            news_str += "\n"

    header = f"## {normalized} News, from {start_date} to {end_date}:\n\n"
    return header + news_str


# ── Global / market news ────────────────────────────────────────────────

def get_global_news(
    curr_date: Annotated[str, "current date in yyyy-mm-dd format"],
    look_back_days: Optional[int] = None,
    limit: Optional[int] = None,
) -> str:
    """Retrieve global/market financial news via akshare.

    Uses East Money's market news feed for Chinese market context.
    """
    import akshare as ak

    config = get_config()
    if look_back_days is None:
        look_back_days = config.get("global_news_lookback_days", 7)
    if limit is None:
        limit = config.get("global_news_article_limit", 10)

    try:
        # East Money financial news
        df = _ak_retry(ak.stock_news_em, symbol="000001")  # broad market news
    except Exception:
        df = None

    # Fallback: CCTV news
    if df is None or df.empty:
        try:
            df = _ak_retry(ak.news_cctv, date=curr_date.replace("-", ""))
        except Exception:
            return f"No global news found for {curr_date}"

    if df is None or df.empty:
        return f"No global news found for {curr_date}"

    # Filter by date range
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)

    # Try to find a date column
    date_col = None
    for candidate in ["发布时间", "date", "pub_date", "datetime"]:
        if candidate in df.columns:
            date_col = candidate
            break

    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df[df[date_col].notna()]
        df = df[(df[date_col] >= start_dt) & (df[date_col] <= curr_dt + timedelta(days=1))]
        df = df.sort_values(date_col, ascending=False)

    df = df.head(limit)

    if df.empty:
        return f"No global news found for {curr_date}"

    news_str = ""
    title_col = None
    for candidate in ["新闻标题", "title", "content"]:
        if candidate in df.columns:
            title_col = candidate
            break

    for _, row in df.iterrows():
        if title_col:
            title = str(row[title_col]).strip()
            if title and title != "nan":
                news_str += f"### {title}\n"

                # Try to get content
                content_col = None
                for candidate in ["新闻内容", "content", "desc", "summary"]:
                    if candidate in df.columns:
                        content_col = candidate
                        break
                if content_col and content_col != title_col:
                    content = str(row.get(content_col, "")).strip()
                    if content and content != "nan":
                        if len(content) > 300:
                            content = content[:300] + "..."
                        news_str += f"{content}\n"

                # Try to get source
                source_col = None
                for candidate in ["文章来源", "source", "media"]:
                    if candidate in df.columns:
                        source_col = candidate
                        break
                if source_col:
                    source = str(row.get(source_col, "")).strip()
                    if source and source != "nan":
                        news_str += f"Source: {source}\n"

                news_str += "\n"

    start_date = start_dt.strftime("%Y-%m-%d")
    header = f"## China Market News, from {start_date} to {curr_date}:\n\n"
    return header + news_str
