"""Korean market data vendor.

Stage 2 prefers ``pykrx`` (KRX-native OHLCV + supply/demand) when it is
installed and the request returns usable data, and falls back to the existing
Yahoo Finance vendor for Korean tickers (``.KS``/``.KQ``) when pykrx is
unavailable, errors out, or returns an empty frame. This keeps Korean-only
sources opt-in while leaving the analyst tools wired the same way.

Stage 3 layers in OpenDART (https://opendart.fss.or.kr/) disclosure and
financial-statement context on top of the yfinance fundamentals baseline.
DART access is fully optional: it activates only when ``DART_API_KEY`` or
``OPENDART_API_KEY`` is set, and any network/API failure degrades to a note
section rather than blocking the baseline report.
"""

from __future__ import annotations

import html
import io
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from functools import lru_cache

import requests

from .y_finance import (
    get_YFin_data_online,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_fundamentals as get_yfinance_fundamentals,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance

KOREA_SUFFIXES = (".KS", ".KQ")

DART_CORPCODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_FNLTT_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
DART_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
DART_HTTP_TIMEOUT = 10
NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"
NAVER_HTTP_TIMEOUT = 10


def is_korean_ticker(ticker: str) -> bool:
    """Return True for Yahoo-style KOSPI/KOSDAQ tickers."""
    return ticker.upper().endswith(KOREA_SUFFIXES)


def _with_korea_context(title: str, ticker: str, body: str) -> str:
    market_note = (
        "Korea market context: treat Yahoo Finance data as a baseline only. "
        "For stronger Korean-stock analysis, augment with DART filings, KRX/pykrx "
        "supply-demand data, Korean-language news, and local investor-community signals."
    )
    return f"# {title} for {ticker}\n\n{market_note}\n\n{body}"


def to_pykrx_ticker(ticker: str) -> str:
    """Strip the Yahoo ``.KS``/``.KQ`` suffix so pykrx receives the bare KRX code."""
    upper = ticker.upper()
    for suffix in KOREA_SUFFIXES:
        if upper.endswith(suffix):
            return upper[: -len(suffix)]
    return upper


def _to_pykrx_date(date_str: str) -> str:
    """Convert ``YYYY-MM-DD`` to pykrx's ``YYYYMMDD`` format."""
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y%m%d")


# Korean → English column hints used in the markdown table header so LLM
# consumers do not need to interpret Hangul column names directly.
_OHLCV_COLUMN_LABELS = {
    "시가": "Open",
    "고가": "High",
    "저가": "Low",
    "종가": "Close",
    "거래량": "Volume",
    "거래대금": "TradingValue",
    "등락률": "ChangePct",
}


def _format_pykrx_ohlcv_markdown(df, ticker: str, start_date: str, end_date: str) -> str:
    """Render a pykrx OHLCV frame as a markdown table with bilingual headers."""
    import pandas as pd  # local import keeps module importable without pandas at parse time

    frame = df.copy()
    if isinstance(frame.index, pd.DatetimeIndex):
        frame.index = frame.index.strftime("%Y-%m-%d")
    frame.index.name = "날짜 (Date)"

    rounded_columns = ("시가", "고가", "저가", "종가", "등락률")
    for col in rounded_columns:
        if col in frame.columns:
            frame[col] = frame[col].round(2)

    renamed = {col: f"{col} ({_OHLCV_COLUMN_LABELS[col]})" for col in frame.columns if col in _OHLCV_COLUMN_LABELS}
    frame = frame.rename(columns=renamed)

    header = (
        f"## OHLCV (pykrx) for {ticker} from {start_date} to {end_date}\n"
        f"Rows: {len(frame)}\n"
    )
    return header + "\n" + frame.to_markdown()


_INVESTOR_TABLE_LABELS = {
    "trading_value": ("Investor trading value (KRW)", "거래대금 / Trading Value (KRW)"),
    "trading_volume": ("Investor trading volume (shares)", "거래량 / Trading Volume (shares)"),
}


def _format_investor_table(df, kind: str) -> str:
    import pandas as pd

    title, axis_label = _INVESTOR_TABLE_LABELS[kind]
    frame = df.copy()
    if isinstance(frame.index, pd.DatetimeIndex):
        frame.index = frame.index.strftime("%Y-%m-%d")
    frame.index.name = "날짜 (Date)"
    return f"### {title}\n_{axis_label}_\n\n" + frame.to_markdown()


def _fetch_pykrx_stock_data(ticker: str, start_date: str, end_date: str) -> str | None:
    """Return a markdown report using pykrx, or ``None`` to signal fallback.

    Returns ``None`` when pykrx is not installed, the OHLCV frame is empty, or
    the OHLCV call raises — letting the caller route to the yfinance baseline.
    Supply/demand sections are best-effort: a failure there only adds a note.
    """
    try:
        from pykrx import stock as krx_stock  # type: ignore
    except ImportError:
        return None

    krx_ticker = to_pykrx_ticker(ticker)
    pkx_start = _to_pykrx_date(start_date)
    pkx_end = _to_pykrx_date(end_date)

    try:
        ohlcv = krx_stock.get_market_ohlcv(pkx_start, pkx_end, krx_ticker)
    except Exception:
        return None

    if ohlcv is None or getattr(ohlcv, "empty", True):
        return None

    sections = [_format_pykrx_ohlcv_markdown(ohlcv, ticker, start_date, end_date)]

    investor_notes = []
    investor_fetchers = (
        ("trading_value", "get_market_trading_value_by_date"),
        ("trading_volume", "get_market_trading_volume_by_date"),
    )
    for kind, fn_name in investor_fetchers:
        fetcher = getattr(krx_stock, fn_name, None)
        if fetcher is None:
            investor_notes.append(f"- pykrx supply/demand `{fn_name}` not available in this version.")
            continue
        try:
            frame = fetcher(pkx_start, pkx_end, krx_ticker)
        except Exception as exc:  # network / KRX schema drift / etc.
            investor_notes.append(f"- pykrx {kind} fetch failed: {type(exc).__name__}: {exc}")
            continue
        if frame is None or getattr(frame, "empty", True):
            investor_notes.append(f"- pykrx {kind}: no rows returned for this window.")
            continue
        sections.append(_format_investor_table(frame, kind))

    if investor_notes:
        sections.append("### Supply/demand notes\n" + "\n".join(investor_notes))

    return "\n\n".join(sections)


def get_stock_data(ticker: str, start_date: str, end_date: str) -> str:
    """Return OHLCV data for Korean tickers, preferring pykrx with yfinance fallback."""
    if is_korean_ticker(ticker):
        pykrx_report = _fetch_pykrx_stock_data(ticker, start_date, end_date)
        if pykrx_report is not None:
            return _with_korea_context("Korean stock price data", ticker, pykrx_report)
        data = get_YFin_data_online(ticker, start_date, end_date)
        return _with_korea_context("Korean stock price data", ticker, data)
    return get_YFin_data_online(ticker, start_date, end_date)


def get_indicators(ticker: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    from .y_finance import get_stock_stats_indicators_window

    data = get_stock_stats_indicators_window(ticker, indicator, curr_date, look_back_days)
    if is_korean_ticker(ticker):
        return _with_korea_context("Korean technical indicators", ticker, data)
    return data


# ---------------------------------------------------------------------------
# OpenDART helpers
# ---------------------------------------------------------------------------


def _dart_api_key() -> str | None:
    """Return the configured OpenDART API key, if any."""
    return os.environ.get("DART_API_KEY") or os.environ.get("OPENDART_API_KEY")


def _dart_no_key_note() -> str:
    return (
        "### DART context\n"
        "_DART API key not configured (set `DART_API_KEY` or `OPENDART_API_KEY` to enable "
        "OpenDART filings and financial-statement augmentation)._"
    )


def _parse_corp_code_zip(content: bytes) -> dict[str, dict[str, str]]:
    """Parse the ``corpCode.xml`` ZIP payload into a stock_code → record map.

    Only entries with a non-empty ``stock_code`` (i.e. listed companies) are
    kept since unlisted issuers are not addressable through Yahoo tickers.
    """
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        xml_name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
        if xml_name is None:
            return {}
        with zf.open(xml_name) as xml_file:
            tree = ET.parse(xml_file)
    root = tree.getroot()
    mapping: dict[str, dict[str, str]] = {}
    for node in root.findall("list"):
        stock_code = (node.findtext("stock_code") or "").strip()
        if not stock_code:
            continue
        mapping[stock_code] = {
            "corp_code": (node.findtext("corp_code") or "").strip(),
            "corp_name": (node.findtext("corp_name") or "").strip(),
            "stock_code": stock_code,
            "modify_date": (node.findtext("modify_date") or "").strip(),
        }
    return mapping


@lru_cache(maxsize=1)
def _load_corp_code_map() -> dict[str, dict[str, str]]:
    """Fetch and cache the OpenDART corp-code ZIP. Returns ``{}`` on failure."""
    api_key = _dart_api_key()
    if not api_key:
        return {}
    try:
        response = requests.get(
            DART_CORPCODE_URL,
            params={"crtfc_key": api_key},
            timeout=DART_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        return _parse_corp_code_zip(response.content)
    except Exception:
        return {}


def _resolve_corp_code(ticker: str) -> dict[str, str] | None:
    """Map a Yahoo-style Korean ticker to its OpenDART corp record, or ``None``."""
    stock_code = to_pykrx_ticker(ticker)
    record = _load_corp_code_map().get(stock_code)
    return record or None


def _format_recent_filings(corp_code: str, curr_date: str) -> str:
    """Return a markdown section of the latest disclosures, or a note on failure."""
    try:
        end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError:
        return "### DART recent filings\n_Invalid curr_date; skipped._"
    bgn_dt = end_dt - timedelta(days=365)
    api_key = _dart_api_key()
    if not api_key:
        return "### DART recent filings\n_API key missing; skipped._"

    try:
        response = requests.get(
            DART_LIST_URL,
            params={
                "crtfc_key": api_key,
                "corp_code": corp_code,
                "bgn_de": bgn_dt.strftime("%Y%m%d"),
                "end_de": end_dt.strftime("%Y%m%d"),
                "page_count": 10,
            },
            timeout=DART_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return (
            "### DART recent filings\n"
            f"_DART list.json call failed: {type(exc).__name__}: {exc}._"
        )

    status = str(payload.get("status", ""))
    rows = payload.get("list") or []
    if status != "000" or not rows:
        message = payload.get("message") or "no rows returned"
        return f"### DART recent filings\n_No recent disclosures ({message})._"

    lines = [
        "### DART recent filings",
        f"_Window: {bgn_dt.strftime('%Y-%m-%d')} → {end_dt.strftime('%Y-%m-%d')} (latest {len(rows)})_",
        "",
        "| Date | Report | Filer |",
        "| --- | --- | --- |",
    ]
    pipe_escape = "\\|"
    for row in rows:
        rcept_no = (row.get("rcept_no") or "").strip()
        report_nm = (row.get("report_nm") or "").strip()
        rcept_dt = (row.get("rcept_dt") or "").strip()
        flr_nm = (row.get("flr_nm") or "").strip()
        title = report_nm.replace("|", pipe_escape) or "(untitled)"
        if rcept_no:
            link = DART_VIEWER_URL.format(rcept_no=rcept_no)
            title_cell = f"[{title}]({link})"
        else:
            title_cell = title
        filer_cell = flr_nm.replace("|", pipe_escape)
        lines.append(f"| {rcept_dt} | {title_cell} | {filer_cell} |")
    return "\n".join(lines)


# OpenDART account-name normalization so the markdown summary is human-readable
# regardless of whether a filing uses Korean-only or English-only labels.
_FNLTT_ACCOUNT_LABELS = {
    "ifrs-full_Revenue": "Revenue",
    "ifrs-full_GrossProfit": "Gross profit",
    "ifrs-full_ProfitLossFromOperatingActivities": "Operating profit",
    "ifrs-full_ProfitLoss": "Net income",
    "ifrs-full_Assets": "Total assets",
    "ifrs-full_Liabilities": "Total liabilities",
    "ifrs-full_Equity": "Total equity",
    "ifrs-full_CashFlowsFromUsedInOperatingActivities": "Cash from operating",
    "ifrs-full_CashFlowsFromUsedInInvestingActivities": "Cash from investing",
    "ifrs-full_CashFlowsFromUsedInFinancingActivities": "Cash from financing",
}


def _format_financial_summary(corp_code: str, curr_date: str) -> str:
    """Return a markdown summary of the latest annual report, or a note on failure."""
    api_key = _dart_api_key()
    if not api_key:
        return "### DART financial summary\n_API key missing; skipped._"
    try:
        end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError:
        return "### DART financial summary\n_Invalid curr_date; skipped._"
    bsns_year = end_dt.year - 1

    try:
        response = requests.get(
            DART_FNLTT_URL,
            params={
                "crtfc_key": api_key,
                "corp_code": corp_code,
                "bsns_year": str(bsns_year),
                "reprt_code": "11011",
                "fs_div": "CFS",
            },
            timeout=DART_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return (
            "### DART financial summary\n"
            f"_DART fnlttSinglAcntAll.json call failed: {type(exc).__name__}: {exc}._"
        )

    status = str(payload.get("status", ""))
    rows = payload.get("list") or []
    if status != "000" or not rows:
        message = payload.get("message") or "no rows returned"
        return (
            "### DART financial summary\n"
            f"_No financial statement rows for FY{bsns_year} ({message})._"
        )

    summary: dict[str, dict[str, str]] = {}
    for row in rows:
        account_id = (row.get("account_id") or "").strip()
        if account_id not in _FNLTT_ACCOUNT_LABELS:
            continue
        label = _FNLTT_ACCOUNT_LABELS[account_id]
        entry = summary.setdefault(
            label,
            {
                "current": (row.get("thstrm_amount") or "").strip(),
                "prior": (row.get("frmtrm_amount") or "").strip(),
                "sj_div": (row.get("sj_div") or "").strip(),
            },
        )
        # Prefer the first occurrence but fill blanks from later rows when needed.
        if not entry["current"]:
            entry["current"] = (row.get("thstrm_amount") or "").strip()
        if not entry["prior"]:
            entry["prior"] = (row.get("frmtrm_amount") or "").strip()

    if not summary:
        return (
            "### DART financial summary\n"
            f"_FY{bsns_year} report fetched, but no recognized account_ids matched._"
        )

    lines = [
        "### DART financial summary",
        f"_FY{bsns_year} consolidated annual report (reprt_code=11011)._",
        "",
        "| Account | Current period | Prior period |",
        "| --- | ---: | ---: |",
    ]
    for label in _FNLTT_ACCOUNT_LABELS.values():
        if label not in summary:
            continue
        entry = summary[label]
        lines.append(f"| {label} | {entry['current'] or '-'} | {entry['prior'] or '-'} |")
    return "\n".join(lines)


def _dart_context_sections(
    ticker: str,
    curr_date: str,
    *,
    include_filings: bool = True,
    include_financials: bool = True,
) -> str:
    """Assemble the DART context block, never raising — failures become notes."""
    try:
        if not _dart_api_key():
            return _dart_no_key_note()
        record = _resolve_corp_code(ticker)
        if not record:
            return (
                "### DART context\n"
                f"_No corp_code mapping for stock_code `{to_pykrx_ticker(ticker)}` "
                "(corp list fetch failed or ticker is unlisted on OpenDART)._"
            )
        corp_code = record["corp_code"]
        corp_name = record.get("corp_name") or ""
        header = (
            "### DART context\n"
            f"_Mapped {to_pykrx_ticker(ticker)} → corp_code `{corp_code}`"
            f"{f' ({corp_name})' if corp_name else ''}._"
        )
        sections = [header]
        if include_filings:
            sections.append(_format_recent_filings(corp_code, curr_date))
        if include_financials:
            sections.append(_format_financial_summary(corp_code, curr_date))
        return "\n\n".join(sections)
    except Exception as exc:
        return (
            "### DART context\n"
            f"_Unexpected DART pipeline error: {type(exc).__name__}: {exc}._"
        )


def get_fundamentals(ticker: str, curr_date: str) -> str:
    data = get_yfinance_fundamentals(ticker, curr_date)
    if is_korean_ticker(ticker):
        dart_block = _dart_context_sections(ticker, curr_date)
        body = f"{data}\n\n{dart_block}"
        return _with_korea_context("Korean fundamentals baseline", ticker, body)
    return data


def get_balance_sheet(ticker: str, curr_date: str) -> str:
    data = get_yfinance_balance_sheet(ticker, curr_date)
    if is_korean_ticker(ticker):
        dart_block = _dart_context_sections(ticker, curr_date, include_filings=False)
        body = f"{data}\n\n{dart_block}"
        return _with_korea_context("Korean balance sheet baseline", ticker, body)
    return data


def get_cashflow(ticker: str, curr_date: str) -> str:
    data = get_yfinance_cashflow(ticker, curr_date)
    if is_korean_ticker(ticker):
        dart_block = _dart_context_sections(ticker, curr_date, include_filings=False)
        body = f"{data}\n\n{dart_block}"
        return _with_korea_context("Korean cash flow baseline", ticker, body)
    return data


def get_income_statement(ticker: str, curr_date: str) -> str:
    data = get_yfinance_income_statement(ticker, curr_date)
    if is_korean_ticker(ticker):
        dart_block = _dart_context_sections(ticker, curr_date, include_filings=False)
        body = f"{data}\n\n{dart_block}"
        return _with_korea_context("Korean income statement baseline", ticker, body)
    return data


# ---------------------------------------------------------------------------
# Korean-language news helpers (Naver Search API)
# ---------------------------------------------------------------------------


def _naver_news_credentials() -> tuple[str, str] | None:
    """Return configured Naver Search API credentials, if any."""
    client_id = os.environ.get("NAVER_NEWS_CLIENT_ID") or os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_NEWS_CLIENT_SECRET") or os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    return client_id, client_secret


def _strip_html(text: str) -> str:
    """Remove Naver's HTML highlights and decode entities."""
    return re.sub(r"<[^>]+>", "", html.unescape(text or "")).strip()


def _korean_news_query(ticker: str) -> str:
    """Use DART corp_name when available, otherwise fall back to the bare stock code."""
    corp_name = ""
    if _dart_api_key():
        try:
            record = _resolve_corp_code(ticker)
            corp_name = (record or {}).get("corp_name", "")
        except Exception:
            corp_name = ""
    code = to_pykrx_ticker(ticker)
    return f"{corp_name} {code} 주식".strip() if corp_name else f"{code} 주식"


def _format_korean_news(ticker: str, start_date: str, end_date: str, *, display: int = 10) -> str:
    """Return Naver Korean-news search results as markdown, never raising."""
    creds = _naver_news_credentials()
    if not creds:
        return (
            "### Korean-language news (Naver)\n"
            "_Naver Search API credentials not configured (set `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET` "
            "or `NAVER_NEWS_CLIENT_ID`/`NAVER_NEWS_CLIENT_SECRET` to enable Korean-news augmentation)._"
        )
    client_id, client_secret = creds
    query = _korean_news_query(ticker)
    try:
        response = requests.get(
            NAVER_NEWS_URL,
            params={"query": query, "display": display, "sort": "date"},
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
            },
            timeout=NAVER_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return (
            "### Korean-language news (Naver)\n"
            f"_Naver news API call failed: {type(exc).__name__}: {exc}._"
        )

    items = payload.get("items") or []
    lines = [
        "### Korean-language news (Naver)",
        f"_Query: `{query}`. Requested analysis window: {start_date} → {end_date}._",
        "_Naver Search API does not provide strict date-range filtering here; results may fall outside the requested window._",
        "",
    ]
    if not items:
        lines.append("_No Korean-news search results returned._")
        return "\n".join(lines)

    for item in items[:display]:
        title = _strip_html(item.get("title", "")) or "(untitled)"
        description = _strip_html(item.get("description", ""))
        pub_date = _strip_html(item.get("pubDate", "")) or "date unknown"
        link = item.get("originallink") or item.get("link") or ""
        if link:
            headline = f"[{title}]({link})"
        else:
            headline = title
        if description:
            lines.append(f"- {pub_date}: {headline} — {description}")
        else:
            lines.append(f"- {pub_date}: {headline}")
    return "\n".join(lines)


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    data = get_news_yfinance(ticker, start_date, end_date)
    if is_korean_ticker(ticker):
        korean_news = _format_korean_news(ticker, start_date, end_date)
        return _with_korea_context("Korean news baseline", ticker, f"{data}\n\n{korean_news}")
    return data


def get_global_news(curr_date: str, look_back_days: int | None = None, limit: int | None = None) -> str:
    return get_global_news_yfinance(curr_date, look_back_days, limit)


def get_insider_transactions(ticker: str) -> str:
    data = get_yfinance_insider_transactions(ticker)
    if is_korean_ticker(ticker):
        return _with_korea_context("Korean insider-transactions baseline", ticker, data)
    return data
