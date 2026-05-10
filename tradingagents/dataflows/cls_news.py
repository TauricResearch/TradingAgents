"""CLS (财联社) flash news for HK / Shanghai / Shenzhen tickers.

CLS is the de-facto real-time market headline service for mainland China —
short, fast flashes that surface market-moving events minutes after they
break, distinct from Eastmoney's longer editorial articles. We pull the
global flash stream via akshare and filter by ticker code or company-name
mention, so the analyst sees both the breaking event and Eastmoney's
journalism explainer of it.

Returned content is Chinese-language. The trading-agents pipeline reads
it natively (MiMo / Kimi / DeepSeek all handle Chinese without
translation overhead).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from .eastmoney_news import _split_ticker  # ticker-suffix parsing reused
from .stockstats_utils import normalize_ticker_for_yfinance

logger = logging.getLogger(__name__)


# In-process cache: ticker -> short company name. Resolved via yfinance
# (already a hard dep) so we can match articles that name the issuer.
_NAME_CACHE: dict[str, Optional[str]] = {}


def _resolve_company_short_name(ticker: str) -> Optional[str]:
    """One-shot ticker -> short Chinese-or-English issuer name. Best-effort.

    yfinance only accepts ``.SS`` for Shanghai; ``.SH`` (which Chinese
    platforms commonly use) raises 404. We normalise here so users can
    paste tickers in either convention without losing the name lookup.
    """
    if ticker in _NAME_CACHE:
        return _NAME_CACHE[ticker]
    try:
        import yfinance as yf
        info = yf.Ticker(normalize_ticker_for_yfinance(ticker)).info or {}
        name = info.get("shortName") or info.get("longName")
        if isinstance(name, str):
            for tail in (" Limited", " Ltd.", " Ltd", " Group", " Holdings", " Corporation", " Co"):
                if name.endswith(tail):
                    name = name[: -len(tail)].strip()
        _NAME_CACHE[ticker] = name
        return name
    except Exception as e:  # pragma: no cover
        logger.debug("CLS name lookup failed for %s: %s", ticker, e)
        _NAME_CACHE[ticker] = None
        return None


def _matches(haystack: str, needles: List[str]) -> bool:
    haystack_l = haystack.lower()
    return any(n and n.lower() in haystack_l for n in needles)


def get_news_cls(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Fetch CLS flash news mentioning the ticker.

    Args mirror :func:`get_news_yfinance` for drop-in compatibility with
    the auto-router. Returns Markdown; on any error returns a labelled
    marker rather than raising.
    """
    parts = _split_ticker(ticker)
    if parts is None:
        return f"[CLS skip — {ticker} has no exchange suffix]"
    code, suffix = parts
    if suffix not in ("HK", "SS", "SH", "SZ"):
        return f"[CLS skip — {suffix} suffix routed elsewhere]"

    try:
        import akshare as ak
    except ImportError:
        return "[CLS unavailable: install `akshare` for Chinese-market flash news.]"

    try:
        # Global flash stream, ~20 most-recent items. CLS doesn't expose a
        # per-ticker filter, so we fetch the stream and match locally.
        df = ak.stock_info_global_cls(symbol="全部")
    except Exception as e:
        logger.warning("CLS stock_info_global_cls failed: %s", e)
        return f"[CLS fetch failed: {type(e).__name__}: {e}]"

    if df is None or df.empty:
        return f"No CLS flash news available for {ticker}."

    # Build matching needles: ticker code, normalised forms, and company name.
    needles: List[str] = [code, code.lstrip("0")]
    if suffix == "HK":
        # CLS articles often use the bare 5-digit Hong Kong code without leading zeros
        needles.append(code.zfill(5))
    company = _resolve_company_short_name(ticker)
    if company:
        needles.append(company)
        first_word = company.split()[0] if company.split() else ""
        if first_word and first_word.upper() != code and len(first_word) >= 2:
            needles.append(first_word)

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        start_dt = end_dt = None

    matches: List[dict] = []
    for _, row in df.iterrows():
        title = str(row.get("标题", "")).strip()
        body = str(row.get("内容", "")).strip()
        date_str = str(row.get("发布日期", "")).strip()
        time_str = str(row.get("发布时间", "")).strip()

        if not title and not body:
            continue
        if not _matches(title + " " + body, needles):
            continue

        published: Optional[datetime] = None
        if date_str:
            try:
                published = datetime.strptime(f"{date_str} {time_str}".strip(), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    published = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    published = None

        if start_dt and end_dt and published is not None:
            if not (start_dt <= published <= end_dt):
                continue

        matches.append({
            "title": title,
            "body": body,
            "published": published,
        })

    if not matches:
        return f"No CLS flash news matching {ticker} between {start_date} and {end_date}."

    blocks = []
    for m in matches[:10]:
        block = f"### {m['title']}"
        if m["published"]:
            block += f"  \n*Flash: {m['published'].strftime('%Y-%m-%d %H:%M')}*"
        if m["body"]:
            block += f"\n{m['body']}"
        blocks.append(block)

    header = (
        f"## {ticker} flash news (CLS / 财联社), {start_date} to {end_date}\n"
        f"*Real-time market-moving headlines. Source: cls.cn via akshare.*\n"
    )
    return header + "\n\n".join(blocks)
