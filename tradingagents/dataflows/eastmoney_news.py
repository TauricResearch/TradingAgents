"""Eastmoney (东方财富) news data source for HK / SH / SZ tickers.

The default yfinance news pipeline is English-only and very sparse for
Asian-listed counters. Eastmoney is the de-facto financial news portal in
mainland China and covers all three exchanges (HK / Shanghai / Shenzhen)
in a single API. We use the ``akshare`` library as a stable wrapper over
Eastmoney's reverse-engineered endpoints — the schema can shift but the
maintainers track it.

Returned content is **Chinese-language**. The trading-agents pipeline
runs MiMo / Kimi / DeepSeek which all read Chinese natively; passing
this through to the analyst is what unlocks meaningful coverage of
Asian-market tickers.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# Suffix -> (akshare-symbol formatter, market label).
# Eastmoney uses bare digit codes: 6-digit for A-shares, 5-digit zero-padded
# for HK. The akshare wrapper accepts both transparently. ``.SH`` and ``.SS``
# both refer to the Shanghai exchange — different platforms use either form.
_SUFFIX_FORMATTERS = {
    "SS": (lambda code: code.zfill(6), "Shanghai A-share"),
    "SH": (lambda code: code.zfill(6), "Shanghai A-share"),
    "SZ": (lambda code: code.zfill(6), "Shenzhen A-share"),
    "HK": (lambda code: code.zfill(5), "Hong Kong"),
}


def _split_ticker(ticker: str) -> Optional[Tuple[str, str]]:
    """``"600519.SS"`` -> ``("600519", "SS")``. Returns None if no suffix."""
    if not ticker or "." not in ticker:
        return None
    code, suffix = ticker.rsplit(".", 1)
    return code, suffix.upper()


def _to_eastmoney_symbol(ticker: str) -> Optional[Tuple[str, str]]:
    """Map a TradingAgents-style ticker to (eastmoney_symbol, market_label).

    Returns None if the suffix is not one Eastmoney covers — caller falls
    back to yfinance in that case.
    """
    parts = _split_ticker(ticker)
    if parts is None:
        return None
    code, suffix = parts
    fmt = _SUFFIX_FORMATTERS.get(suffix)
    if fmt is None:
        return None
    formatter, label = fmt
    return formatter(code), label


def _parse_publish_time(raw: object) -> Optional[datetime]:
    """Eastmoney returns timestamps like '2026-04-25 10:15:22'. Be permissive."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def get_news_eastmoney(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Fetch recent news for an HK / Shanghai / Shenzhen ticker from Eastmoney.

    Args mirror :func:`get_news_yfinance` so this is a drop-in replacement
    selected by the auto-routing vendor.

    Returns a Markdown-formatted string with up to ~10 articles. On any
    error returns a labelled error string so the analyst sees the issue
    rather than a silent empty report.
    """
    mapped = _to_eastmoney_symbol(ticker)
    if mapped is None:
        return f"[Eastmoney skip — {ticker} has no .HK/.SS/.SZ suffix]"

    em_symbol, market_label = mapped

    try:
        # Imported lazily so the rest of the pipeline does not pay the
        # akshare import cost when the user never analyses an HK/CN ticker.
        import akshare as ak
    except ImportError:
        return (
            "[Eastmoney news unavailable: install `akshare` to enable Chinese "
            "news for HK / Shanghai / Shenzhen tickers.]"
        )

    try:
        df = ak.stock_news_em(symbol=em_symbol)
    except Exception as e:
        logger.warning("akshare stock_news_em failed for %s: %s", em_symbol, e)
        return f"[Eastmoney fetch failed for {ticker}: {type(e).__name__}: {e}]"

    if df is None or df.empty:
        return f"No Eastmoney news found for {ticker} ({market_label})."

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        # Bad date input — return everything Eastmoney returned without filtering.
        start_dt = None
        end_dt = None

    pieces = []
    for _, row in df.iterrows():
        title = str(row.get("新闻标题", "")).strip()
        body = str(row.get("新闻内容", "")).strip()
        source = str(row.get("文章来源", "")).strip()
        link = str(row.get("新闻链接", "")).strip()
        published = _parse_publish_time(row.get("发布时间"))

        if start_dt and end_dt and published is not None:
            if not (start_dt <= published <= end_dt):
                continue

        if not title:
            continue
        block = f"### {title}"
        if source:
            block += f" (source: {source})"
        if published:
            block += f"  \n*Published: {published.strftime('%Y-%m-%d %H:%M')}*"
        if body:
            block += f"\n{body}"
        if link:
            block += f"\nLink: {link}"
        pieces.append(block)

    if not pieces:
        return (
            f"No Eastmoney news for {ticker} ({market_label}) between "
            f"{start_date} and {end_date}."
        )

    header = (
        f"## {ticker} News from Eastmoney (东方财富, {market_label}), "
        f"{start_date} to {end_date}\n"
        f"*Note: source content is Chinese-language; the analyst LLM reads it natively.*\n"
    )
    return header + "\n\n".join(pieces)
