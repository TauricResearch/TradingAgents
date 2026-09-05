"""Eastmoney F10 finance vendor for A-share fundamentals and statements."""

from __future__ import annotations

import logging
import re
from datetime import datetime

import pandas as pd
import requests

from .errors import NoMarketDataError

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "Chrome/124 Safari/537.36"
)
_F10_BASE = "https://emweb.securities.eastmoney.com/PC_HSF10"
_SURVEY_URL = f"{_F10_BASE}/CompanySurvey/PageAjax"
_FINANCE_URL = f"{_F10_BASE}/NewFinanceAnalysis/ZYZBAjaxNew"
_STATEMENT_URLS = {
    "balance": f"{_F10_BASE}/NewFinanceAnalysis/zcfzbAjaxNew",
    "cashflow": f"{_F10_BASE}/NewFinanceAnalysis/xjllbAjaxNew",
    "income": f"{_F10_BASE}/NewFinanceAnalysis/lrbAjaxNew",
}

_META_COLUMNS = {
    "SECUCODE",
    "SECURITY_CODE",
    "SECURITY_NAME_ABBR",
    "ORG_CODE",
    "ORG_TYPE",
    "SECURITY_TYPE_CODE",
    "NOTICE_DATE",
    "UPDATE_DATE",
    "CURRENCY",
    "REPORT_TYPE",
    "REPORT_DATE_NAME",
    "REPORT_YEAR",
}


def _em_code(ticker: str) -> str | None:
    """Map an A-share ticker to Eastmoney's ``SZ000021`` / ``SH601665`` form."""
    match = re.search(r"(\d{6})", ticker)
    if not match:
        return None
    code = match.group(1)
    upper = ticker.upper()
    if upper.endswith(".SS") or upper.endswith(".SH") or code.startswith(("5", "6", "9")):
        return f"SH{code}"
    return f"SZ{code}"


def _fetch_json(url: str, params: dict) -> dict:
    last: Exception | None = None
    for _ in range(3):
        try:
            resp = requests.get(
                url,
                params=params,
                headers={"User-Agent": _UA, "Referer": "https://emweb.securities.eastmoney.com/"},
                timeout=25,
            )
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last = exc
            logger.warning("Eastmoney F10 request failed for %s: %s", params, exc)
    raise NoMarketDataError(
        str(params.get("code", "")),
        str(params.get("code", "")),
        f"Eastmoney F10 unavailable: {type(last).__name__}",
    ) from last


def _report_dates(ticker: str, freq: str, curr_date: str | None) -> list[str]:
    code = _em_code(ticker)
    if not code:
        raise NoMarketDataError(ticker, ticker, "Eastmoney finance supports A-shares only")

    payload = _fetch_json(_FINANCE_URL, {"type": "0", "code": code})
    rows = payload.get("data") or []
    dates = []
    for row in rows:
        date_str = (row.get("REPORT_DATE") or "")[:10]
        if not date_str:
            continue
        if freq.lower() == "annual" and not date_str.endswith("-12-31"):
            continue
        if curr_date and date_str > curr_date:
            continue
        dates.append(date_str)
    return sorted(set(dates), reverse=True)[:4]


def _statement_frame(
    ticker: str,
    statement: str,
    freq: str,
    curr_date: str | None,
) -> tuple[pd.DataFrame, bool]:
    code = _em_code(ticker)
    if not code:
        raise NoMarketDataError(ticker, ticker, "Eastmoney finance supports A-shares only")

    dates = _report_dates(ticker, freq, curr_date)
    if not dates:
        raise NoMarketDataError(ticker, code, "no report dates returned")

    items = []
    used_fallback = False
    url = _STATEMENT_URLS[statement]
    for date_str in dates:
        rows = []
        for company_type in ("8", "4", "1"):
            payload = _fetch_json(
                url,
                {
                    "companyType": company_type,
                    "reportDateType": "0",
                    "reportType": "1",
                    "dates": date_str,
                    "code": code,
                },
            )
            rows = payload.get("data") or []
            if rows:
                break
        if rows:
            items.append(rows[0])

    if not items:
        # Banks and some financial companies do not expose the detailed
        # statement through this endpoint; fall back to Eastmoney's main
        # financial indicators so the tool still returns domestic data.
        payload = _fetch_json(_FINANCE_URL, {"type": "0", "code": code})
        fallback_rows = payload.get("data") or []
        if freq.lower() == "annual":
            fallback_rows = [
                r for r in fallback_rows
                if (r.get("REPORT_DATE") or "")[:10].endswith("-12-31")
            ]
        if curr_date:
            fallback_rows = [
                r for r in fallback_rows
                if (r.get("REPORT_DATE") or "")[:10] <= curr_date
            ]
        fallback_rows = sorted(
            fallback_rows,
            key=lambda r: (r.get("REPORT_DATE") or ""),
            reverse=True,
        )[:4]
        if not fallback_rows:
            raise NoMarketDataError(ticker, code, "no statement rows returned")
        items = fallback_rows
        used_fallback = True

    frame = pd.DataFrame(items)
    frame = frame.drop(columns=[c for c in _META_COLUMNS if c in frame.columns], errors="ignore")
    frame = frame.set_index("REPORT_DATE")
    frame = frame.T
    frame = frame.sort_index(axis=1)
    return frame, used_fallback


def _statement_csv(ticker: str, statement: str, freq: str, curr_date: str | None) -> str:
    frame, fallback = _statement_frame(ticker, statement, freq, curr_date)
    header = f"# {statement} data for {ticker} ({freq})\n"
    if fallback:
        header += "# 东方财富未提供该企业详细报表，以下为主要财务指标降级数据。\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + frame.to_csv()


def get_balance_sheet(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
) -> str:
    return _statement_csv(ticker, "balance", freq, curr_date)


def get_cashflow(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
) -> str:
    return _statement_csv(ticker, "cashflow", freq, curr_date)


def get_income_statement(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
) -> str:
    return _statement_csv(ticker, "income", freq, curr_date)


def resolve_company_survey(ticker: str) -> dict:
    """Resolve deterministic company identity metadata from Eastmoney."""
    code = _em_code(ticker)
    if not code:
        return {}
    try:
        payload = _fetch_json(_SURVEY_URL, {"code": code})
    except NoMarketDataError:
        return {}
    rows = payload.get("jbzl") or []
    if not rows:
        return {}
    row = rows[0]
    identity: dict[str, str] = {}
    name = row.get("ORG_NAME") or row.get("SECURITY_NAME_ABBR")
    if name:
        identity["company_name"] = name
    industry = row.get("EM2016") or row.get("INDUSTRYCSRC1")
    if industry:
        identity["industry"] = industry
    if row.get("TRADE_MARKET"):
        identity["exchange"] = row["TRADE_MARKET"]
    return identity


def get_fundamentals(ticker: str, curr_date: str | None = None) -> str:
    """Return an A-share fundamentals overview from Eastmoney."""
    code = _em_code(ticker)
    if not code:
        raise NoMarketDataError(ticker, ticker, "Eastmoney finance supports A-shares only")

    payload = _fetch_json(_FINANCE_URL, {"type": "2", "code": code})
    rows = payload.get("data") or []
    if not rows:
        raise NoMarketDataError(ticker, code, "no fundamentals returned")

    rows = sorted(rows, key=lambda r: (r.get("REPORT_DATE") or ""), reverse=True)
    if curr_date:
        rows = [r for r in rows if (r.get("REPORT_DATE") or "")[:10] <= curr_date]
    if not rows:
        raise NoMarketDataError(ticker, code, "no fundamentals on or before curr_date")
    latest = rows[0]

    survey = resolve_company_survey(ticker)
    lines = [
        f"Company: {survey.get('company_name', latest.get('SECURITY_NAME_ABBR', ticker))}",
    ]
    if survey.get("industry"):
        lines.append(f"Industry: {survey['industry']}")
    if survey.get("exchange"):
        lines.append(f"Exchange: {survey['exchange']}")

    fields = [
        ("Report Date", latest.get("REPORT_DATE")),
        ("EPS", latest.get("EPSJB")),
        ("BPS", latest.get("BPS")),
        ("Revenue", latest.get("TOTALOPERATEREVE")),
        ("Gross Profit", latest.get("GROSS_PROFIT")),
        ("Gross Margin", latest.get("GROSS_PROFIT_RATIO")),
        ("Net Profit (parent)", latest.get("PARENTNETPROFIT")),
        ("Net Margin", latest.get("NET_PROFIT_RATIO")),
        ("Deducted Net Profit", latest.get("DEDU_PARENT_PROFIT")),
        ("ROE (diluted)", latest.get("ROE_DILUTED")),
        ("ROA", latest.get("JROA")),
    ]
    for label, value in fields:
        if value is not None:
            lines.append(f"{label}: {value}")

    header = f"# Company Fundamentals for {code}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + "\n".join(lines)


def get_insider_transactions(ticker: str) -> str:
    """Insider transactions placeholder sourced from a domestic platform.

    Eastmoney's public F10 feed does not expose a keyless insider-transaction
    endpoint, so we return a clear sentinel instead of calling Yahoo.
    """
    code = _em_code(ticker) or ticker
    return f"暂无东方财富高管增减持公开接口数据（{code}）。"
