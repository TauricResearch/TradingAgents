"""AKShare vendor for Chinese A-share market data.

Provides OHLCV prices, news, fundamentals, and sentiment from domestic
Chinese data sources (东方财富, 同花顺, etc.) for stocks traded on the
Shanghai (.SS) and Shenzhen (.SZ) exchanges.

Data sources used:
  - 东方财富 (eastmoney.com) — price history, news, announcements, hot rank
  - 同花顺 (ths.com)         — financial abstract (income, margins, ROE …)
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# Chinese domestic data hosts must NOT be routed through a VPN/proxy. A foreign
# proxy node (e.g. Clash on 127.0.0.1:7897) corrupts the TLS stream to these
# servers, surfacing as `SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC`. requests /
# urllib3 honor NO_PROXY by host-suffix, and akshare itself uses bare
# `requests.get` internally — so extending NO_PROXY here transparently makes
# both akshare's calls and ours bypass the proxy for domestic endpoints.
# (Note: this cannot defeat a system-wide TUN/transparent proxy, which
# intercepts below the application layer — that must be fixed in the VPN.)
_DOMESTIC_HOSTS = (
    "eastmoney.com", "10jqka.com.cn", "sina.com.cn", "hexun.com",
    "sse.com.cn", "szse.cn", "cninfo.com.cn",
)


def _ensure_domestic_no_proxy() -> None:
    for var in ("NO_PROXY", "no_proxy"):
        existing = [h for h in os.environ.get(var, "").split(",") if h]
        for host in _DOMESTIC_HOSTS:
            if host not in existing:
                existing.append(host)
        os.environ[var] = ",".join(existing)


_ensure_domestic_no_proxy()


def _no_proxy_dict() -> dict:
    """Explicit per-call proxy override for libraries that ignore NO_PROXY."""
    return {"http": None, "https": None}


# ── Ticker helpers ────────────────────────────────────────────────────────────

def is_a_share(ticker: str) -> bool:
    """True when ticker is a Chinese A-share (Yahoo Finance .SS/.SZ suffix)."""
    u = ticker.upper()
    return u.endswith(".SS") or u.endswith(".SZ")


def _to_akshare_code(ticker: str) -> str:
    """Strip the Yahoo exchange suffix: '600519.SS' → '600519'."""
    return ticker.split(".")[0]


def _em_prefix(code: str) -> str:
    """Return the 东方财富 market prefix used by hot-rank: 'SH600519'."""
    return ("SH" if code.startswith("6") else "SZ") + code


def _fmt_date_ak(date_str: str) -> str:
    """'yyyy-mm-dd' → 'yyyymmdd' for AKShare date parameters."""
    return date_str.replace("-", "")


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


# ── Price data ────────────────────────────────────────────────────────────────

def get_stock_data_akshare(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """OHLCV price data for an A-share via 东方财富/AKShare."""
    try:
        import akshare as ak

        code = _to_akshare_code(ticker)
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=_fmt_date_ak(start_date),
            end_date=_fmt_date_ak(end_date),
            adjust="qfq",
        )
        if df.empty:
            return (
                f"NO_DATA_AVAILABLE: No market data found for A-share '{ticker}'. "
                f"The code '{code}' may be invalid or delisted."
            )

        df = df.rename(columns={
            "日期": "Date", "股票代码": "Code",
            "开盘": "Open",  "收盘": "Close",
            "最高": "High",  "最低": "Low",
            "成交量": "Volume", "成交额": "Amount",
            "振幅": "Amplitude", "涨跌幅": "PctChange",
            "涨跌额": "Change",  "换手率": "Turnover",
        })

        header = (
            f"# A-share price data for {ticker} (code: {code})\n"
            f"# Period: {start_date} to {end_date}  |  Records: {len(df)}\n"
            f"# Source: 东方财富 via AKShare (前复权/qfq adjusted)\n\n"
        )
        return header + df.to_csv(index=False)
    except Exception as e:
        logger.warning("AKShare price fetch failed for %s: %s", ticker, e)
        raise


# ── Technical indicators ───────────────────────────────────────────────────────

def _load_ohlcv_akshare(ticker: str, curr_date: str):
    """5-year OHLCV from AKShare in stockstats-compatible format."""
    import akshare as ak
    import pandas as pd

    code = _to_akshare_code(ticker)
    start = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=365 * 5)).strftime("%Y%m%d")
    end = datetime.strptime(curr_date, "%Y-%m-%d").strftime("%Y%m%d")
    df = ak.stock_zh_a_hist(
        symbol=code, period="daily",
        start_date=start, end_date=end,
        adjust="qfq",
    )
    if df.empty:
        raise ValueError(f"No AKShare OHLCV data for {ticker}")

    df = df.rename(columns={
        "日期": "Date", "开盘": "Open", "最高": "High",
        "最低": "Low",  "收盘": "Close", "成交量": "Volume",
    })
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df[df["Date"] <= pd.to_datetime(curr_date)].reset_index(drop=True)
    return df


_INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50 SMA: medium-term trend; dynamic support/resistance.",
    "close_200_sma": "200 SMA: long-term benchmark; golden/death cross.",
    "close_10_ema": "10 EMA: short-term momentum; quick entry signals.",
    "macd":  "MACD: EMA-difference momentum; watch for crossovers.",
    "macds": "MACD Signal: EMA of MACD; crossover trigger.",
    "macdh": "MACD Histogram: momentum gap; divergence signal.",
    "rsi":   "RSI: overbought >70 / oversold <30.",
    "boll":  "Bollinger Middle: 20 SMA baseline.",
    "boll_ub": "Bollinger Upper: overbought / breakout zone.",
    "boll_lb": "Bollinger Lower: oversold level.",
    "atr":   "ATR: volatility measure for stop-loss sizing.",
    "vwma":  "VWMA: volume-weighted moving average.",
    "mfi":   "MFI: money flow index; >80 overbought, <20 oversold.",
}


def get_indicators_akshare(
    ticker: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
) -> str:
    """Technical indicators for an A-share computed from AKShare OHLCV data."""
    try:
        from stockstats import wrap
        import pandas as pd
        from dateutil.relativedelta import relativedelta

        data = _load_ohlcv_akshare(ticker, curr_date)
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        df[indicator]  # trigger stockstats computation

        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        before = curr_dt - relativedelta(days=look_back_days)
        ind_lines = ""
        ptr = curr_dt
        while ptr >= before:
            ds = ptr.strftime("%Y-%m-%d")
            rows = df[df["Date"] == ds]
            val = rows[indicator].values[0] if not rows.empty else "N/A: not a trading day"
            ind_lines += f"{ds}: {val}\n"
            ptr -= relativedelta(days=1)

        desc = _INDICATOR_DESCRIPTIONS.get(indicator, "")
        return (
            f"## {indicator} for A-share {ticker} "
            f"({before.strftime('%Y-%m-%d')} → {curr_date}):\n\n"
            + ind_lines
            + f"\n{desc}"
        )
    except Exception as e:
        logger.warning("AKShare indicators failed for %s/%s: %s", ticker, indicator, e)
        raise


# ── News (eastmoney search API) ───────────────────────────────────────────────

def _fetch_em_news(query: str, n: int = 25) -> list[dict]:
    """Fetch news articles from 东方财富 search API (JSONP endpoint)."""
    try:
        from curl_cffi import requests as cffi_req

        url = "https://search-api-web.eastmoney.com/search/jsonp"
        params = {
            "cb": "cb",
            "param": json.dumps({
                "uid": "", "keyword": query,
                "type": ["cmsArticle"],
                "client": "web", "clientVersion": "curr",
                "param": {
                    "cmsArticle": {
                        "searchScope": "default",
                        "sort": "date",
                        "pageIndex": 1,
                        "pageSize": n,
                    }
                },
            }),
            "_": "1640829691088",
        }
        headers = {
            "referer": f"https://so.eastmoney.com/news/s?keyword={query}",
            "user-agent": "Mozilla/5.0",
        }
        r = cffi_req.get(url, params=params, headers=headers, timeout=10,
                         impersonate="chrome110", proxies=_no_proxy_dict())
        m = re.search(r"^[^(]+\((.*)\)$", r.text.strip(), re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group(1))
        articles = data.get("result", {}).get("cmsArticle", [])
        if isinstance(articles, dict):
            articles = articles.get("data", [])
        return articles or []
    except Exception as exc:
        logger.warning("东方财富 news fetch failed (query=%r): %s", query, exc)
        raise


def get_news_akshare(ticker: str, start_date: str, end_date: str) -> str:
    """Recent news for an A-share from 东方财富."""
    code = _to_akshare_code(ticker)
    articles = _fetch_em_news(code, n=40)

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    filtered = []
    for a in articles:
        ds = a.get("date", "")[:10]
        try:
            if start_dt <= datetime.strptime(ds, "%Y-%m-%d") <= end_dt:
                filtered.append(a)
        except ValueError:
            filtered.append(a)

    # Fall back to all recent articles if none fall in window
    display = filtered if filtered else articles[:25]

    if not display:
        return f"<No 东方财富 news found for A-share {ticker}>"

    lines = [
        f"# 东方财富 news for A-share {ticker} ({start_date} → {end_date})",
        f"# Articles shown: {len(display)}",
        "",
    ]
    for a in display:
        title = _strip_html(a.get("title", ""))
        date = a.get("date", "")[:16]
        source = a.get("mediaName", "")
        lines.append(f"[{date}] [{source}] {title}")

    return "\n".join(lines)


def get_global_news_akshare(
    curr_date: str,
    lookback_days: Optional[int] = None,
    limit: Optional[int] = None,
) -> str:
    """Broad Chinese market news from 东方财富."""
    n = limit or 20
    articles = _fetch_em_news("A股 市场 宏观", n=n)
    if not articles:
        return f"<Chinese market news temporarily unavailable ({curr_date})>"

    lines = [
        f"# 东方财富 Chinese market news ({curr_date})",
        f"# Articles: {len(articles)}",
        "",
    ]
    for a in articles[:n]:
        title = _strip_html(a.get("title", ""))
        date = a.get("date", "")[:16]
        source = a.get("mediaName", "")
        lines.append(f"[{date}] [{source}] {title}")

    return "\n".join(lines)


# ── Fundamentals (同花顺 financial abstract) ──────────────────────────────────

def _get_financial_abstract(ticker: str) -> "pd.DataFrame":
    import akshare as ak
    code = _to_akshare_code(ticker)
    return ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")


def get_fundamentals_akshare(ticker: str) -> str:
    """Key financial metrics (income, margins, ROE …) via 同花顺."""
    try:
        df = _get_financial_abstract(ticker)
        if df.empty:
            return f"NO_DATA_AVAILABLE: No financial data for A-share '{ticker}'."
        header = (
            f"# 同花顺 financial abstract for A-share {ticker}\n"
            f"# Source: 同花顺 via AKShare  |  Periods shown: {min(8, len(df))}\n\n"
        )
        return header + df.head(8).to_csv(index=False)
    except Exception as e:
        logger.warning("AKShare fundamentals failed for %s: %s", ticker, e)
        return f"<A-share fundamentals unavailable for {ticker}: {type(e).__name__}>"


def get_income_statement_akshare(ticker: str) -> str:
    """Income statement proxy — selects revenue/profit columns from abstract."""
    try:
        df = _get_financial_abstract(ticker)
        if df.empty:
            return f"NO_DATA_AVAILABLE: No income data for '{ticker}'."
        keep = [c for c in df.columns if any(k in c for k in
               ["报告期", "净利润", "营业", "收入", "利润", "EPS", "每股收益", "毛利"])]
        cols = keep if keep else list(df.columns)[:10]
        return (
            f"# 同花顺 income statement (proxy) for A-share {ticker}\n\n"
            + df[cols].head(8).to_csv(index=False)
        )
    except Exception as e:
        return f"<A-share income statement unavailable for {ticker}: {type(e).__name__}>"


def get_balance_sheet_akshare(ticker: str) -> str:
    """Balance sheet proxy — selects asset/liability columns from abstract."""
    try:
        df = _get_financial_abstract(ticker)
        if df.empty:
            return f"NO_DATA_AVAILABLE: No balance sheet data for '{ticker}'."
        keep = [c for c in df.columns if any(k in c for k in
               ["报告期", "资产", "负债", "净资产", "股东权益", "每股净资产", "资产负债率"])]
        cols = keep if keep else list(df.columns)[:10]
        return (
            f"# 同花顺 balance sheet (proxy) for A-share {ticker}\n\n"
            + df[cols].head(8).to_csv(index=False)
        )
    except Exception as e:
        return f"<A-share balance sheet unavailable for {ticker}: {type(e).__name__}>"


def get_cashflow_akshare(ticker: str) -> str:
    """Cash-flow proxy — selects cash-related columns from abstract."""
    try:
        df = _get_financial_abstract(ticker)
        if df.empty:
            return f"NO_DATA_AVAILABLE: No cash flow data for '{ticker}'."
        keep = [c for c in df.columns if any(k in c for k in
               ["报告期", "现金", "经营", "投资", "筹资", "自由现金", "每股现金"])]
        cols = keep if keep else list(df.columns)[:10]
        return (
            f"# 同花顺 cash flow (proxy) for A-share {ticker}\n\n"
            + df[cols].head(8).to_csv(index=False)
        )
    except Exception as e:
        return f"<A-share cash flow unavailable for {ticker}: {type(e).__name__}>"


# ── Official announcements (公告) ─────────────────────────────────────────────

def get_insider_transactions_akshare(ticker: str) -> str:
    """Official company announcements as proxy for insider / major-shareholder activity."""
    try:
        code = _to_akshare_code(ticker)
        url = (
            "https://np-anotice-stock.eastmoney.com/api/security/ann"
            f"?sr=-1&page_size=20&page_index=1&ann_type=A"
            f"&client_source=web&stock_list={code}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        # Domestic host: force a direct (no-proxy) opener so a VPN can't break it.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=10) as r:
            data = json.loads(r.read())

        items = (data.get("data") or {}).get("list") or []
        if not items:
            return f"<No recent announcements found for A-share {ticker}>"

        lines = [
            f"# 东方财富 official announcements for A-share {ticker}",
            f"# Count: {len(items)}",
            "",
        ]
        for item in items:
            lines.append(f"[{item.get('display_time','')[:16]}] {item.get('title','')}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("AKShare announcements failed for %s: %s", ticker, e)
        return f"<A-share announcements unavailable for {ticker}: {type(e).__name__}>"


# ── Social sentiment (热度排行 proxy) ─────────────────────────────────────────

def fetch_guba_posts(ticker: str) -> str:
    """Market heat-rank context as A-share social sentiment proxy.

    Chinese retail sentiment platforms (股吧, 雪球) require authentication;
    this uses 东方财富's public hot-rank feed as a lightweight proxy.
    """
    try:
        import akshare as ak

        code = _to_akshare_code(ticker)
        hot_df = ak.stock_hot_rank_em()

        prefix = _em_prefix(code)
        rows = hot_df[hot_df["代码"] == prefix]

        lines = [f"# 东方财富 heat-rank sentiment context for A-share {ticker}"]

        if not rows.empty:
            row = rows.iloc[0]
            rank = row.get("当前排名", "?")
            price = row.get("最新价", "?")
            pct = row.get("涨跌幅", "?")
            lines.append(
                f"# {ticker} is ranked #{rank} in retail-investor attention today "
                f"(price: {price}, change: {pct}%)"
            )
            lines.append(
                "# Interpretation: A top-10 ranking signals high social media buzz; "
                "outside top-50 suggests relatively low retail attention."
            )
        else:
            lines.append(
                f"# {ticker} is NOT in the 东方财富 top hot-stocks list today, "
                f"suggesting below-average retail attention / social media activity."
            )

        lines.append("")
        lines.append("## Top-10 most-watched A-shares today (market sentiment context):")
        for _, r in hot_df.head(10).iterrows():
            lines.append(
                f"  [{r['当前排名']}] {r['股票名称']} ({r['代码']})  "
                f"change: {r['涨跌幅']}%"
            )

        lines.append("")
        lines.append(
            "Note: 股吧 / 雪球 individual post data is unavailable without "
            "authentication. The heat-rank and news-sentiment from 东方财富 "
            "serve as the primary retail-sentiment signal for this A-share."
        )
        return "\n".join(lines)
    except Exception as e:
        logger.warning("AKShare heat-rank failed for %s: %s", ticker, e)
        return (
            f"<A-share social sentiment (heat-rank) data temporarily unavailable "
            f"for {ticker}: {type(e).__name__}>"
        )
