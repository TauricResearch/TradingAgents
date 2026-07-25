"""EastMoney direct-HTTP A-share specialty data adapters.

Replaces the former akshare-wrapped specialty layer (dragon-tiger, lockups,
block trades, shareholder counts, limit-up pool) with direct EastMoney
datacenter/push2ex calls.  akshare wrapped the same EastMoney endpoints;
talking to them directly removes the SDK failure layer (akfamily/akshare
issues #7101, #7103, #6148) and matches a-stock-data SKILL.md §3/§8.

Each adapter returns a source-labelled markdown report or raises
``ChinaDataUnavailableError``; it never fabricates rows when EastMoney changes
a schema or throttles the IP.  The dragon-tiger board additionally carries an
official exchange backup (``get_a_share_dragon_tiger_official``) on an
independent rate-limit plane, for when EastMoney bans the IP.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import requests

from .china_data import ChinaDataUnavailableError
from .eastmoney import EASTMONEY_DATACENTER_URL, _extract_records, em_get
from .ticker_utils import is_a_share_ticker, normalize_ticker_symbol, to_akshare_symbol

_EASTMONEY_QUOTE_REFERER = "https://quote.eastmoney.com/"
_ZTB_UT = "7eea3edcaed734bea9cbfc24409ed989"
_ZTB_URL = "https://push2ex.eastmoney.com/"
_REPORT_API_URL = "https://reportapi.eastmoney.com/report/list"
_INDUSTRY_CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
_SLIST_URL = "https://push2.eastmoney.com/api/qt/slist/get"


def _eastmoney_datacenter(
    report_name: str,
    *,
    filter_str: str = "",
    page_size: int = 50,
    sort_columns: str = "",
    sort_types: str = "-1",
    columns: str = "ALL",
) -> list[dict[str, Any]]:
    """Query the EastMoney datacenter; return result rows or empty list."""
    payload = em_get(
        EASTMONEY_DATACENTER_URL,
        params={
            "reportName": report_name,
            "columns": columns,
            "filter": filter_str,
            "pageNumber": "1",
            "pageSize": str(page_size),
            "sortColumns": sort_columns,
            "sortTypes": sort_types,
            "source": "WEB",
            "client": "WEB",
        },
    )
    return _extract_records(payload)


def _require_a_share_code(ticker: str) -> str:
    canonical = normalize_ticker_symbol(ticker)
    if not is_a_share_ticker(canonical):
        raise ChinaDataUnavailableError(f"{ticker} is not recognized as an A-share ticker.")
    return to_akshare_symbol(canonical)


def _format_report(
    data: pd.DataFrame,
    *,
    title: str,
    caveat: str,
    source: str = "eastmoney",
) -> str:
    if data.empty:
        raise ChinaDataUnavailableError(f"{source} returned no rows for {title}.")
    return "\n".join(
        [
            f"# {title}",
            f"# Source: {source}",
            f"# Note: {caveat}",
            f"# Total records: {len(data)}",
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            data.to_csv(index=False),
        ]
    )


def _capture_vendor_raw(data: Any, *, metadata: dict[str, Any]) -> None:
    from tradingagents.observability.provenance import capture_vendor_raw

    capture_vendor_raw(data, metadata=dict(metadata))


def get_a_share_dragon_tiger_em(ticker: str, trade_date: str, flag: str = "买入") -> str:
    """A-share dragon-tiger board (个股龙虎榜) via EastMoney datacenter direct.

    Returns appearance records within a 30-day look-back from ``trade_date``
    plus TOP5 buy/sell seats for the latest appearance.  ``flag`` is accepted
    for signature compatibility with the former akshare adapter; EastMoney
    returns both sides in one call.
    """
    code = _require_a_share_code(ticker)
    start = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
    records = _eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=f"(TRADE_DATE>='{start}')(TRADE_DATE<='{trade_date}')(SECURITY_CODE=\"{code}\")",
        page_size=50,
        sort_columns="TRADE_DATE",
        sort_types="-1",
    )
    if not records:
        raise ChinaDataUnavailableError(f"EastMoney returned no dragon-tiger records for {code}.")
    records_df = pd.DataFrame(
        [
            {
                "Date": str(r.get("TRADE_DATE", ""))[:10],
                "Reason": r.get("EXPLANATION", ""),
                "Net Buy (wan)": round((r.get("BILLBOARD_NET_AMT") or 0) / 10000, 1),
                "Turnover %": round(float(r.get("TURNOVERRATE") or 0), 2),
            }
            for r in records
        ]
    )
    seats_rows: list[dict[str, Any]] = []
    latest_date = records_df["Date"].iloc[0]
    for side, report_name, sort_col in (
        ("buy", "RPT_BILLBOARD_DAILYDETAILSBUY", "BUY"),
        ("sell", "RPT_BILLBOARD_DAILYDETAILSSELL", "SELL"),
    ):
        detail = _eastmoney_datacenter(
            report_name,
            filter_str=f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{code}\")",
            page_size=10,
            sort_columns=sort_col,
            sort_types="-1",
        )
        for row in detail[:5]:
            seats_rows.append(
                {
                    "Side": side,
                    "Seat": row.get("OPERATEDEPT_NAME", ""),
                    "Buy (wan)": round((row.get("BUY") or 0) / 10000, 1),
                    "Sell (wan)": round((row.get("SELL") or 0) / 10000, 1),
                    "Net (wan)": round((row.get("NET") or 0) / 10000, 1),
                }
            )
    _capture_vendor_raw(
        {"records": records, "seats": seats_rows},
        metadata={"provider": "eastmoney", "dataset": "dragon_tiger", "ticker": ticker},
    )
    report = _format_report(
        records_df,
        title=f"China A-share dragon-tiger records for {normalize_ticker_symbol(ticker)}",
        caveat=f"EastMoney datacenter; 30-day look-back from {trade_date}; flag '{flag}' accepted but both sides returned.",
    )
    if seats_rows:
        report += f"\n\n## TOP5 buy/sell seats on {latest_date}\n\n" + pd.DataFrame(seats_rows).to_csv(index=False)
    return report


def get_a_share_lockup_releases_em(ticker: str, start_date: str, end_date: str) -> str:
    """A-share lockup-release calendar (限售解禁) via EastMoney datacenter direct."""
    code = _require_a_share_code(ticker)
    history = _eastmoney_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=15,
        sort_columns="FREE_DATE",
        sort_types="-1",
    )
    upcoming = _eastmoney_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=f'(SECURITY_CODE="{code}")(FREE_DATE>=\'{start_date}\')(FREE_DATE<=\'{end_date}\')',
        page_size=20,
        sort_columns="FREE_DATE",
        sort_types="1",
    )
    rows: list[dict[str, Any]] = []
    for scope, src in (("history", history), ("upcoming", upcoming)):
        for r in src:
            rows.append(
                {
                    "Scope": scope,
                    "Date": str(r.get("FREE_DATE", ""))[:10],
                    "Type": r.get("FREE_SHARES_TYPE", ""),
                    "Shares (wan)": r.get("FREE_SHARES", 0),
                    "Able Shares (wan)": r.get("ABLE_FREE_SHARES", 0),
                    "Ratio": r.get("FREE_RATIO", 0),
                }
            )
    if not rows:
        raise ChinaDataUnavailableError(f"EastMoney returned no lockup-release rows for {code}.")
    _capture_vendor_raw(
        {"history": history, "upcoming": upcoming},
        metadata={"provider": "eastmoney", "dataset": "lockup_releases", "ticker": ticker},
    )
    return _format_report(
        pd.DataFrame(rows),
        title=f"China A-share lockup releases for {normalize_ticker_symbol(ticker)}",
        caveat="EastMoney datacenter RPT_LIFT_STAGE; FREE_SHARES_TYPE/FREE_SHARES are the 2026-renamed columns; ABLE_FREE_SHARES is actually-tradable shares.",
    )


def get_a_share_bulk_trades_em(ticker: str, start_date: str, end_date: str) -> str:
    """A-share block trades (大宗交易) via EastMoney datacenter direct."""
    code = _require_a_share_code(ticker)
    data = _eastmoney_datacenter(
        "RPT_DATA_BLOCKTRADE",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=30,
        sort_columns="TRADE_DATE",
        sort_types="-1",
    )
    rows = []
    for r in data:
        close = r.get("CLOSE_PRICE") or 0
        deal = r.get("DEAL_PRICE") or 0
        premium = ((deal / close - 1) * 100) if close else 0
        rows.append(
            {
                "Date": str(r.get("TRADE_DATE", ""))[:10],
                "Deal Price": deal,
                "Close": close,
                "Premium %": round(premium, 2),
                "Volume": r.get("DEAL_VOLUME", 0),
                "Amount": r.get("DEAL_AMT", 0),
                "Buyer": r.get("BUYER_NAME", ""),
                "Seller": r.get("SELLER_NAME", ""),
            }
        )
    if not rows:
        raise ChinaDataUnavailableError(f"EastMoney returned no block-trade rows for {code}.")
    _capture_vendor_raw(data, metadata={"provider": "eastmoney", "dataset": "bulk_trades", "ticker": ticker})
    return _format_report(
        pd.DataFrame(rows),
        title=f"China A-share block trades for {normalize_ticker_symbol(ticker)}",
        caveat="EastMoney datacenter RPT_DATA_BLOCKTRADE; premium % is deal price vs close.",
    )


def get_a_share_shareholder_counts_em(ticker: str) -> str:
    """A-share shareholder-count changes (股东户数) via EastMoney datacenter direct."""
    code = _require_a_share_code(ticker)
    data = _eastmoney_datacenter(
        "RPT_HOLDERNUMLATEST",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=10,
        sort_columns="END_DATE",
        sort_types="-1",
    )
    rows = [
        {
            "Date": str(r.get("END_DATE", ""))[:10],
            "Holder Num": r.get("HOLDER_NUM", 0),
            "Change Num": r.get("HOLDER_NUM_CHANGE", 0),
            "Change %": r.get("HOLDER_NUM_RATIO", 0),
            "Avg Hold Num": r.get("AVG_HOLD_NUM", 0),
        }
        for r in data
    ]
    if not rows:
        raise ChinaDataUnavailableError(f"EastMoney returned no shareholder-count rows for {code}.")
    _capture_vendor_raw(data, metadata={"provider": "eastmoney", "dataset": "shareholder_counts", "ticker": ticker})
    return _format_report(
        pd.DataFrame(rows),
        title=f"China A-share shareholder counts for {normalize_ticker_symbol(ticker)}",
        caveat="EastMoney datacenter RPT_HOLDERNUMLATEST; quarterly; declining holder count signals chip concentration.",
    )


def _em_zt_api(endpoint: str, sort: str, date: str) -> list[dict[str, Any]]:
    """Fetch a limit-board pool from EastMoney push2ex (throttled via em_get).

    endpoint: getTopicZTPool / getTopicZBPool / getTopicDTPool / getYesterdayZTPool.
    Returns ``data.pool`` rows; an empty list means non-trading day or
    after-hours not-yet-updated.
    """
    payload = em_get(
        f"{_ZTB_URL}{endpoint}",
        params={
            "ut": _ZTB_UT,
            "dpt": "wz.ztzt",
            "Pageindex": 0,
            "pagesize": 10000,
            "sort": sort,
            "date": date.replace("-", "") if "-" in date else date,
        },
        headers={"Referer": _EASTMONEY_QUOTE_REFERER},
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return []
    pool = data.get("pool")
    return pool if isinstance(pool, list) else []


def _em_zt_pool(date: str) -> list[dict[str, Any]]:
    """Limit-up pool (涨停池) -- named wrapper for the primary pool."""
    return _em_zt_api("getTopicZTPool", "fbt:asc", date)


def get_a_share_limit_up_ladder_em(trade_date: str) -> str:
    """A-share limit-up pool (涨停池) via EastMoney push2ex direct."""
    pool = _em_zt_pool(trade_date)
    if not pool:
        raise ChinaDataUnavailableError(
            f"EastMoney returned no limit-up pool rows for {trade_date} (non-trading day or after-hours not updated)."
        )
    rows = [
        {
            "Code": p.get("c"),
            "Name": p.get("n"),
            "Price": (p.get("p") or 0) / 1000,
            "Pct %": round(p.get("zdp", 0), 2),
            "Limit Days": p.get("lbc"),
            "Seal Fund": p.get("fund"),
            "Break Times": p.get("zbc"),
            "Industry": p.get("hybk", ""),
            "ZT Stat": f'{(p.get("zttj") or {}).get("days", "?")}天{(p.get("zttj") or {}).get("ct", "?")}板',
        }
        for p in pool
    ]
    _capture_vendor_raw(pool, metadata={"provider": "eastmoney", "dataset": "limit_up_ladder", "ticker": None})
    return _format_report(
        pd.DataFrame(rows),
        title=f"China A-share limit-up pool for {trade_date}",
        caveat="EastMoney push2ex getTopicZTPool; price is raw/1000; non-trading day returns null.",
    )


def get_a_share_break_board_pool(trade_date: str) -> str:
    """A-share break-board pool (炸板池, 涨停后开板) via EastMoney push2ex direct."""
    pool = _em_zt_api("getTopicZBPool", "fbt:asc", trade_date)
    if not pool:
        raise ChinaDataUnavailableError(
            f"EastMoney returned no break-board pool rows for {trade_date} (non-trading day or after-hours not updated)."
        )
    rows = [
        {
            "Code": p.get("c"),
            "Name": p.get("n"),
            "Price": (p.get("p") or 0) / 1000,
            "Limit Price": (p.get("ztp") or 0) / 1000,
            "Pct %": round(p.get("zdp", 0), 2),
            "Turnover %": round(p.get("hs", 0), 2),
            "Break Times": p.get("zbc"),
            "Amplitude %": round(p.get("zf", 0), 2),
            "Speed %": round(p.get("zs", 0), 2),
            "Industry": p.get("hybk", ""),
        }
        for p in pool
    ]
    _capture_vendor_raw(pool, metadata={"provider": "eastmoney", "dataset": "break_board_pool", "ticker": None})
    return _format_report(
        pd.DataFrame(rows),
        title=f"China A-share break-board pool for {trade_date}",
        caveat="EastMoney push2ex getTopicZBPool; stocks that hit limit-up then opened; price/limit_price are raw/1000.",
    )


def get_a_share_limit_down_pool(trade_date: str) -> str:
    """A-share limit-down pool (跌停池) via EastMoney push2ex direct."""
    pool = _em_zt_api("getTopicDTPool", "fund:asc", trade_date)
    if not pool:
        raise ChinaDataUnavailableError(
            f"EastMoney returned no limit-down pool rows for {trade_date} (non-trading day or after-hours not updated)."
        )
    rows = [
        {
            "Code": p.get("c"),
            "Name": p.get("n"),
            "Price": (p.get("p") or 0) / 1000,
            "Pct %": round(p.get("zdp", 0), 2),
            "Turnover %": round(p.get("hs", 0), 2),
            "Seal Fund": p.get("fund"),
            "Limit Down Days": p.get("days"),
            "Open Times": p.get("oc"),
            "Industry": p.get("hybk", ""),
        }
        for p in pool
    ]
    _capture_vendor_raw(pool, metadata={"provider": "eastmoney", "dataset": "limit_down_pool", "ticker": None})
    return _format_report(
        pd.DataFrame(rows),
        title=f"China A-share limit-down pool for {trade_date}",
        caveat="EastMoney push2ex getTopicDTPool; price is raw/1000; seal fund in yuan.",
    )


def get_a_share_prev_limit_up_pool(trade_date: str) -> str:
    """A-share previous-day limit-up pool (昨涨停今表现) via EastMoney push2ex direct."""
    pool = _em_zt_api("getYesterdayZTPool", "zs:desc", trade_date)
    if not pool:
        raise ChinaDataUnavailableError(
            f"EastMoney returned no previous-day limit-up pool rows for {trade_date} (non-trading day or after-hours not updated)."
        )
    rows = [
        {
            "Code": p.get("c"),
            "Name": p.get("n"),
            "Price": (p.get("p") or 0) / 1000,
            "Pct %": round(p.get("zdp", 0), 2),
            "Turnover %": round(p.get("hs", 0), 2),
            "Amplitude %": round(p.get("zf", 0), 2),
            "Speed %": round(p.get("zs", 0), 2),
            "Prev Limit Days": p.get("ylbc"),
            "Industry": p.get("hybk", ""),
        }
        for p in pool
    ]
    _capture_vendor_raw(pool, metadata={"provider": "eastmoney", "dataset": "prev_limit_up_pool", "ticker": None})
    return _format_report(
        pd.DataFrame(rows),
        title=f"China A-share previous-day limit-up pool for {trade_date}",
        caveat="EastMoney push2ex getYesterdayZTPool; yesterday's limit-up stocks' performance today; price is raw/1000.",
    )


def get_a_share_daily_dragon_tiger(trade_date: str) -> str:
    """Market-wide dragon-tiger board (全市场龙虎榜) for one trade date."""
    data = _eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=f"(TRADE_DATE>='{trade_date}')(TRADE_DATE<='{trade_date}')",
        page_size=500,
        sort_columns="BILLBOARD_NET_AMT",
        sort_types="-1",
    )
    rows = [
        {
            "Code": r.get("SECURITY_CODE", ""),
            "Name": r.get("SECURITY_NAME_ABBR", ""),
            "Reason": r.get("EXPLANATION", ""),
            "Close": r.get("CLOSE_PRICE") or 0,
            "Change %": round(float(r.get("CHANGE_RATE") or 0), 2),
            "Net Buy (wan)": round((r.get("BILLBOARD_NET_AMT") or 0) / 10000, 1),
            "Buy (wan)": round((r.get("BILLBOARD_BUY_AMT") or 0) / 10000, 1),
            "Sell (wan)": round((r.get("BILLBOARD_SELL_AMT") or 0) / 10000, 1),
        }
        for r in data
    ]
    if not rows:
        raise ChinaDataUnavailableError(f"EastMoney returned no market-wide dragon-tiger rows for {trade_date}.")
    _capture_vendor_raw(data, metadata={"provider": "eastmoney", "dataset": "daily_dragon_tiger", "ticker": None})
    return _format_report(
        pd.DataFrame(rows),
        title=f"China A-share market-wide dragon-tiger for {trade_date}",
        caveat="EastMoney datacenter RPT_DAILYBILLBOARD_DETAILSNEW; ranked by net buy; non-trading day returns empty.",
    )


def get_a_share_dragon_tiger_official(trade_date: str) -> str:
    """Official dragon-tiger backup (沪深交易所官方) -- backup for EastMoney.

    SZSE returns structured rows; SSE returns raw text (fileContents).  This is
    an independent rate-limit plane from EastMoney, used when EastMoney bans
    the IP.  Used as the ``china_exchange`` fallback vendor in the router.
    """
    rows: list[dict[str, Any]] = []
    # SZSE: structured
    try:
        resp = requests.get(
            "https://www.szse.cn/api/report/ShowReport/data",
            params={
                "SHOWTYPE": "JSON",
                "CATALOGID": "1842_xxpl",
                "TABKEY": "tab1",
                "txtStart": trade_date,
                "txtEnd": trade_date,
                "random": "0.9",
            },
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.szse.cn/disclosure/supervision/dealinfo/index.html"},
            timeout=15,
        )
        szse_data = resp.json()
        if isinstance(szse_data, list) and szse_data:
            for row in (szse_data[0].get("data") or []):
                rows.append(
                    {
                        "Exchange": "SZSE",
                        "Code": row.get("zqdm"),
                        "Name": row.get("zqjc"),
                        "Amount": row.get("cjje"),
                        "Reason": row.get("plyy"),
                    }
                )
    except (requests.RequestException, ValueError):
        pass  # SZSE failed; SSE may still work

    # SSE: raw text (JSONP)
    sse_raw = ""
    try:
        resp = requests.get(
            "https://query.sse.com.cn/infodisplay/showTradePublicFile.do",
            params={"jsonCallBack": "cb", "isPagination": "false", "dateTx": trade_date},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.sse.com.cn/disclosure/diclosure/public/"},
            timeout=15,
        )
        text = resp.text
        if "(" in text and ")" in text:
            try:
                obj = json.loads(text[text.index("(") + 1 : text.rindex(")")])
                sse_raw = "\n".join(obj.get("fileContents", []))
            except (ValueError, json.JSONDecodeError):
                pass
    except requests.RequestException:
        pass

    if not rows and not sse_raw:
        raise ChinaDataUnavailableError(f"Official dragon-tiger backup returned no data for {trade_date}.")
    _capture_vendor_raw(
        {"szse": rows, "sse_raw": sse_raw},
        metadata={"provider": "china_exchange", "dataset": "dragon_tiger_official", "ticker": None},
    )
    report = ""
    if rows:
        report += _format_report(
            pd.DataFrame(rows),
            title=f"China A-share official dragon-tiger (SZSE) for {trade_date}",
            caveat="SZSE official API; independent backup for EastMoney.",
            source="china_exchange",
        )
    if sse_raw:
        report += f"\n\n## SSE official dragon-tiger raw text for {trade_date}\n\n{sse_raw}\n"
    return report


def get_a_share_research_reports(ticker: str, max_pages: int = 3) -> str:
    """A-share research reports (个股研报) via EastMoney reportapi direct.

    Returns published report list with org/title/rating/forecast-EPS fields.
    The ``predictThisYearEps``/``predictNextYearEps`` fields are analyst
    forecasts, distinct from tushare's reported fundamentals.
    """
    code = _require_a_share_code(ticker)
    all_records: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        payload = em_get(
            _REPORT_API_URL,
            params={
                "industryCode": "*",
                "pageSize": "100",
                "industry": "*",
                "rating": "*",
                "ratingChange": "*",
                "beginTime": "2000-01-01",
                "endTime": "2030-01-01",
                "pageNo": str(page),
                "fields": "",
                "qType": "0",
                "orgCode": "",
                "code": code,
                "rcode": "",
                "p": str(page),
                "pageNum": str(page),
                "pageNumber": str(page),
            },
            headers={"Referer": "https://data.eastmoney.com/"},
            timeout=30,
        )
        rows = payload.get("data") or []
        if not rows:
            break
        all_records.extend(rows)
        if page >= (payload.get("TotalPage", 1) or 1):
            break
    if not all_records:
        raise ChinaDataUnavailableError(f"EastMoney returned no research reports for {code}.")
    rows_df = pd.DataFrame(
        [
            {
                "Date": str(r.get("publishDate", ""))[:10],
                "Org": r.get("orgSName", ""),
                "Title": r.get("title", ""),
                "Rating": r.get("emRatingName", ""),
                "EPS This Year": r.get("predictThisYearEps", ""),
                "EPS Next Year": r.get("predictNextYearEps", ""),
                "Industry": r.get("indvInduName", ""),
            }
            for r in all_records
        ]
    )
    _capture_vendor_raw(all_records, metadata={"provider": "eastmoney", "dataset": "research_reports", "ticker": ticker})
    return _format_report(
        rows_df,
        title=f"China A-share research reports for {normalize_ticker_symbol(ticker)}",
        caveat="EastMoney reportapi; EPS fields are analyst forecasts (predictThisYearEps/predictNextYearEps).",
    )


def get_a_share_eps_forecast(ticker: str) -> str:
    """A-share consensus EPS forecast (机构一致预期EPS) via THS (10jqka).

    Parses the THS worth.html table; the 'mean' column is the institutional
    consensus EPS.  Independent of EastMoney's rate-limit plane.
    """
    code = _require_a_share_code(ticker)
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": "https://basic.10jqka.com.cn/",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        raise ChinaDataUnavailableError(f"THS EPS forecast request failed for {ticker}: {type(exc).__name__}") from exc
    resp.encoding = "gbk"
    from io import StringIO

    try:
        dfs = pd.read_html(StringIO(resp.text))
    except ValueError as exc:
        raise ChinaDataUnavailableError(f"THS returned no parseable EPS table for {code}: {exc}") from exc
    target = None
    for df in dfs:
        cols = [str(c) for c in df.columns]
        if any("每股收益" in c or "均值" in c for c in cols):
            target = df
            break
    if target is None:
        target = dfs[0] if dfs else None
    if target is None or target.empty:
        raise ChinaDataUnavailableError(f"THS returned no EPS forecast rows for {code}.")
    _capture_vendor_raw({"html": resp.text[:2000]}, metadata={"provider": "ths", "dataset": "eps_forecast", "ticker": ticker})
    return _format_report(
        target,
        title=f"China A-share consensus EPS forecast for {normalize_ticker_symbol(ticker)}",
        caveat="THS basic.10jqka.com.cn; 'mean' column = institutional consensus EPS; <3 forecast institutions is low-confidence.",
        source="ths",
    )


def get_a_share_industry_ranking(top_n: int = 20) -> str:
    """A-share industry-board ranking (行业板块涨跌排名) via EastMoney push2 clist.

    Returns all ~100 industry boards sorted by change% descending, with
    up/down stock counts and the leading stock per board.
    """
    payload = em_get(
        _INDUSTRY_CLIST_URL,
        params={
            "pn": "1",
            "pz": "100",
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:90+t:2",
            "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
        },
        headers={"Referer": _EASTMONEY_QUOTE_REFERER},
    )
    items = (payload.get("data") or {}).get("diff") or []
    if not items:
        raise ChinaDataUnavailableError("EastMoney returned no industry-board rows.")
    rows = [
        {
            "Rank": i + 1,
            "Name": item.get("f14", ""),
            "Change %": item.get("f3", 0),
            "Code": item.get("f12", ""),
            "Up Count": item.get("f104", 0),
            "Down Count": item.get("f105", 0),
            "Leader": item.get("f140", ""),
            "Leader Change %": item.get("f136", 0),
        }
        for i, item in enumerate(items)
    ]
    _capture_vendor_raw(items, metadata={"provider": "eastmoney", "dataset": "industry_ranking", "ticker": None})
    return _format_report(
        pd.DataFrame(rows),
        title="China A-share industry-board ranking",
        caveat="EastMoney push2 clist (m:90+t:2); sorted by change% desc; ~100 industries.",
    )


def get_a_share_concept_blocks(ticker: str) -> str:
    """A-share board membership (个股板块归属) via EastMoney push2 slist.

    Returns all industry/concept/region boards a stock belongs to, with the
    board code (BK), change%, and leading stock.  Board names are
    self-describing; EastMoney does not separate industry/concept/region.
    """
    code = _require_a_share_code(ticker)
    market_code = 1 if code.startswith("6") else 0
    payload = em_get(
        _SLIST_URL,
        params={
            "fltt": "2",
            "invt": "2",
            "secid": f"{market_code}.{code}",
            "spt": "3",
            "pi": "0",
            "pz": "200",
            "po": "1",
            "fields": "f12,f14,f3,f128",
        },
        headers={"Referer": _EASTMONEY_QUOTE_REFERER},
    )
    diff = (payload.get("data") or {}).get("diff") or {}
    items = diff.values() if isinstance(diff, dict) else diff
    rows = [
        {
            "Board": it.get("f14", ""),
            "Code": it.get("f12", ""),
            "Change %": it.get("f3", ""),
            "Leader": it.get("f128", ""),
        }
        for it in items
    ]
    if not rows:
        raise ChinaDataUnavailableError(f"EastMoney returned no board membership for {code}.")
    _capture_vendor_raw({"diff": diff}, metadata={"provider": "eastmoney", "dataset": "concept_blocks", "ticker": ticker})
    return _format_report(
        pd.DataFrame(rows),
        title=f"China A-share board membership for {normalize_ticker_symbol(ticker)}",
        caveat="EastMoney push2 slist; mixed industry/concept/region boards; board names are self-describing.",
    )
