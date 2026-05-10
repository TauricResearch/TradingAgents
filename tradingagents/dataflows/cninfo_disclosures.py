"""Cninfo (巨潮资讯) regulatory disclosures for Shanghai / Shenzhen tickers.

Cninfo is the official CSRC-mandated disclosure platform — equivalent to
SEC EDGAR for the US market. Every material A-share filing (盈利预警
profit warnings, 关联交易 related-party transactions, 重大资产重组 major
asset restructurings, 回购 buybacks, 高管变动 management changes) lands
here first; news outlets editorialize it afterward.

For a Review-mode pre-trade decision this is the most authoritative
source we can include — the LLM gets the original filing titles and
links rather than a journalist's interpretation.

Limitations:
- A-share only. HK has its own filing infrastructure (HKEX News) that
  isn't exposed cleanly via akshare; for HK we lean on Eastmoney + CLS.
- Only filing titles + links are returned (akshare wrapper limitation);
  the LLM can flag a filing as worth reading and the trader follows the
  link for the full PDF.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import List, Optional

from .eastmoney_news import _split_ticker

logger = logging.getLogger(__name__)


def _build_link(row, code: str) -> str:
    """Return the filing PDF link.

    akshare's wrapper currently emits a ``公告链接`` column directly, but
    the underlying Cninfo API also exposes the link components
    (``announcementId`` + ``orgId``) — and akshare has been observed
    surfacing one schema or the other depending on ticker / pagination.
    Construct the URL from whichever fields are present so a schema
    drift doesn't silently lose data.
    """
    link = str(row.get("公告链接", "")).strip()
    if link:
        return link

    ann_id = str(row.get("announcementId", "")).strip()
    org_id = str(row.get("orgId", "")).strip()
    ann_time = str(row.get("公告时间", "")).strip()
    if ann_id and org_id:
        return (
            f"http://www.cninfo.com.cn/new/disclosure/detail"
            f"?stockCode={code}&announcementId={ann_id}"
            f"&orgId={org_id}&announcementTime={ann_time}"
        )
    return ""


def _fetch_cninfo_with_retry(symbol: str, start_compact: str, end_compact: str, max_retries: int = 1):
    """Run akshare's Cninfo fetch with one retry on transient failures.

    The wrapper has been observed throwing ``KeyError`` or
    "None of [Index([...])] are in the [columns]" when it hits a
    pagination edge inside Cninfo's API. A single retry resolves
    almost all of these; if it persists, we surface the error to the
    caller so the analyst sees the data gap rather than silently
    losing the source.
    """
    import akshare as ak
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return ak.stock_zh_a_disclosure_report_cninfo(
                symbol=symbol,
                market="沪深京",
                category="",
                start_date=start_compact,
                end_date=end_compact,
            )
        except Exception as e:  # akshare surfaces a wide variety of internal errors
            last_exc = e
            if attempt < max_retries:
                logger.info(
                    "Cninfo fetch transient failure for %s (%s); retrying once",
                    symbol, type(e).__name__,
                )
                time.sleep(1.0)
                continue
    assert last_exc is not None
    raise last_exc


def get_disclosures_cninfo(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Fetch Cninfo regulatory disclosures for an A-share ticker.

    Args mirror the ``get_news`` interface so the auto-router can call
    this alongside Eastmoney and CLS without special-casing.

    Returns Markdown; HK / non-A-share tickers get a labelled skip
    marker so the auto-router can drop the result silently.
    """
    parts = _split_ticker(ticker)
    if parts is None:
        return f"[Cninfo skip — {ticker} has no exchange suffix]"
    code, suffix = parts
    if suffix not in ("SS", "SH", "SZ"):
        return f"[Cninfo skip — A-share only ({suffix} not covered)]"

    try:
        import akshare as ak  # noqa: F401 — ImportError guard; _fetch_cninfo_with_retry imports lazily.
    except ImportError:
        return "[Cninfo unavailable: install `akshare` for A-share regulatory filings.]"

    # Cninfo wants YYYYMMDD; tolerate the YYYY-MM-DD inputs the rest of the
    # pipeline uses.
    try:
        start_compact = datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y%m%d")
        end_compact = datetime.strptime(end_date, "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError:
        return f"[Cninfo skip — could not parse date window {start_date} → {end_date}]"

    code_padded = code.zfill(6)
    try:
        df = _fetch_cninfo_with_retry(code_padded, start_compact, end_compact)
    except Exception as e:
        logger.warning("Cninfo disclosure fetch failed for %s: %s", code, e)
        return f"[Cninfo fetch failed for {ticker}: {type(e).__name__}: {e}]"

    if df is None or df.empty:
        return f"No Cninfo filings for {ticker} between {start_date} and {end_date}."

    rows: List[dict] = []
    for _, row in df.iterrows():
        title = str(row.get("公告标题", "")).strip()
        date = str(row.get("公告时间", "")).strip()
        link = _build_link(row, code_padded)
        short_name = str(row.get("简称", "")).strip()
        if not title:
            continue
        rows.append({"title": title, "date": date, "link": link, "short_name": short_name})

    if not rows:
        return f"No Cninfo filings for {ticker} between {start_date} and {end_date}."

    issuer = rows[0]["short_name"] or code
    blocks = []
    # Cap at 30 — disclosure-heavy stocks (e.g. quarter-end) can flood otherwise.
    for r in rows[:30]:
        block = f"### {r['title']}"
        if r["date"]:
            block += f"  \n*Filed: {r['date']}*"
        if r["link"]:
            block += f"\nLink: {r['link']}"
        blocks.append(block)

    header = (
        f"## {ticker} regulatory filings (Cninfo / 巨潮资讯, {issuer}), "
        f"{start_date} to {end_date}\n"
        f"*Source-of-truth A-share disclosures. Source: cninfo.com.cn via akshare. "
        f"Filing titles only — follow the link for the full PDF.*\n"
    )
    return header + "\n\n".join(blocks)
