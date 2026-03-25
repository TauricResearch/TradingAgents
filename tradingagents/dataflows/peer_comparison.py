"""Sector and peer-relative performance comparison."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf


_SECTOR_ETFS: dict[str, str] = {
    "technology": "XLK",
    "healthcare": "XLV",
    "financials": "XLF",
    "energy": "XLE",
    "consumer-discretionary": "XLY",
    "consumer-staples": "XLP",
    "industrials": "XLI",
    "materials": "XLB",
    "real-estate": "XLRE",
    "utilities": "XLU",
    "communication-services": "XLC",
}

_SECTOR_TICKERS: dict[str, list[str]] = {
    "technology": ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "AMD", "CRM"],
    "healthcare": ["UNH", "JNJ", "LLY", "PFE", "ABT", "MRK", "ABBV", "AMGN"],
    "financials": ["JPM", "BAC", "WFC", "GS", "MS", "BLK", "SCHW", "AXP"],
    "energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "VLO", "OXY"],
    "consumer-discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW"],
    "consumer-staples": ["PG", "KO", "PEP", "COST", "WMT", "MDLZ"],
    "industrials": ["CAT", "HON", "UNP", "UPS", "RTX", "GE"],
    "materials": ["LIN", "APD", "SHW", "FCX", "NEM", "NUE"],
    "real-estate": ["PLD", "AMT", "EQIX", "SPG", "PSA", "DLR"],
    "utilities": ["NEE", "DUK", "SO", "AEP", "SRE", "XEL"],
    "communication-services": ["META", "GOOGL", "NFLX", "DIS", "CMCSA", "TMUS"],
}

_SECTOR_NORMALISE: dict[str, str] = {
    "Technology": "technology",
    "Healthcare": "healthcare",
    "Health Care": "healthcare",
    "Financial Services": "financials",
    "Financials": "financials",
    "Energy": "energy",
    "Consumer Cyclical": "consumer-discretionary",
    "Consumer Discretionary": "consumer-discretionary",
    "Consumer Defensive": "consumer-staples",
    "Consumer Staples": "consumer-staples",
    "Industrials": "industrials",
    "Basic Materials": "materials",
    "Materials": "materials",
    "Real Estate": "real-estate",
    "Utilities": "utilities",
    "Communication Services": "communication-services",
}


def _safe_pct(closes: pd.Series, days_back: int) -> Optional[float]:
    if len(closes) < days_back + 1:
        return None
    base = closes.iloc[-(days_back + 1)]
    current = closes.iloc[-1]
    if base == 0:
        return None
    return (current - base) / base * 100


def _ytd_pct(closes: pd.Series) -> Optional[float]:
    if closes.empty:
        return None
    current_year = closes.index[-1].year
    year_closes = closes[closes.index.year == current_year]
    if len(year_closes) < 2:
        return None
    base = year_closes.iloc[0]
    if base == 0:
        return None
    return (closes.iloc[-1] - base) / base * 100


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _download_history(symbols: list[str], curr_date: str = None) -> pd.DataFrame:
    kwargs = {
        "auto_adjust": True,
        "progress": False,
        "threads": True,
    }
    if curr_date:
        end_ts = pd.Timestamp(curr_date) + pd.Timedelta(days=1)
        start_ts = pd.Timestamp(curr_date) - pd.DateOffset(months=7)
        kwargs["start"] = start_ts.strftime("%Y-%m-%d")
        kwargs["end"] = end_ts.strftime("%Y-%m-%d")
    else:
        kwargs["period"] = "6mo"
    return yf.download(symbols, **kwargs)


def get_sector_peers(ticker: str) -> tuple[str, str, list[str]]:
    try:
        info = yf.Ticker(ticker.upper()).info
    except Exception:
        return "Unknown", "", []

    raw_sector = info.get("sector", "")
    sector_key = _SECTOR_NORMALISE.get(raw_sector, raw_sector.lower().replace(" ", "-"))
    peers = [peer for peer in _SECTOR_TICKERS.get(sector_key, []) if peer != ticker.upper()]
    return raw_sector or "Unknown", sector_key, peers


def compute_relative_performance(
    ticker: str,
    sector_key: str,
    peers: list[str],
    curr_date: str = None,
) -> str:
    etf = _SECTOR_ETFS.get(sector_key)
    symbols = [ticker.upper(), *peers[:8]]
    if etf and etf not in symbols:
        symbols.append(etf)

    try:
        history = _download_history(symbols, curr_date=curr_date)
    except Exception as exc:
        return f"Error downloading price data for peer comparison: {exc}"

    if history.empty:
        return "No price data available for peer comparison."

    closes = history.get("Close", pd.DataFrame())
    rows = []
    for symbol in symbols:
        if symbol not in closes.columns:
            continue
        series = closes[symbol].dropna()
        rows.append(
            {
                "symbol": symbol,
                "1W": _safe_pct(series, 5),
                "1M": _safe_pct(series, 21),
                "3M": _safe_pct(series, 63),
                "6M": _safe_pct(series, 126),
                "YTD": _ytd_pct(series),
                "is_target": symbol == ticker.upper(),
                "is_etf": symbol == etf,
            }
        )

    rows.sort(
        key=lambda row: row["3M"] if row["3M"] is not None else float("-inf"),
        reverse=True,
    )
    peer_rows = [row for row in rows if not row["is_etf"]]
    target_rank = next(
        (index + 1 for index, row in enumerate(peer_rows) if row["is_target"]),
        None,
    )
    n_peers = len(peer_rows)

    lines = [
        f"# Relative Performance Analysis: {ticker.upper()}",
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Sector: {sector_key.replace('-', ' ').title()} | Peer rank (3M): {target_rank}/{n_peers}",
        "",
        "| Symbol | Role | 1-Week | 1-Month | 3-Month | 6-Month | YTD |",
        "|--------|------|--------|---------|---------|---------|-----|",
    ]

    for row in rows:
        role = "► TARGET" if row["is_target"] else ("ETF Benchmark" if row["is_etf"] else "Peer")
        lines.append(
            f"| {row['symbol']} | {role} "
            f"| {_fmt_pct(row['1W'])} "
            f"| {_fmt_pct(row['1M'])} "
            f"| {_fmt_pct(row['3M'])} "
            f"| {_fmt_pct(row['6M'])} "
            f"| {_fmt_pct(row['YTD'])} |"
        )

    target_row = next((row for row in rows if row["is_target"]), None)
    etf_row = next((row for row in rows if row["is_etf"]), None)
    if target_row and etf_row:
        lines.extend(
            [
                "",
                "## Alpha vs Sector ETF",
                "",
                f"- **1-Month**: {_fmt_pct(target_row['1M'])} vs ETF {_fmt_pct(etf_row['1M'])}",
                f"- **3-Month**: {_fmt_pct(target_row['3M'])} vs ETF {_fmt_pct(etf_row['3M'])}",
                f"- **6-Month**: {_fmt_pct(target_row['6M'])} vs ETF {_fmt_pct(etf_row['6M'])}",
            ]
        )

    return "\n".join(lines)


def get_peer_comparison_report(ticker: str, curr_date: str = None) -> str:
    sector_display, sector_key, peers = get_sector_peers(ticker)
    if not peers:
        return (
            f"# Peer Comparison: {ticker.upper()}\n\n"
            f"Could not identify sector peers for {ticker}. Sector detected: '{sector_display}'"
        )
    return compute_relative_performance(
        ticker,
        sector_key,
        peers,
        curr_date=curr_date,
    )


def get_sector_relative_report(ticker: str, curr_date: str = None) -> str:
    sector_display, sector_key, _ = get_sector_peers(ticker)
    etf = _SECTOR_ETFS.get(sector_key)
    if not etf:
        return (
            f"# Sector Relative Performance: {ticker.upper()}\n\n"
            f"No ETF benchmark found for sector '{sector_display}'."
        )

    try:
        history = _download_history([ticker.upper(), etf], curr_date=curr_date)
    except Exception as exc:
        return f"Error downloading data for {ticker} vs {etf}: {exc}"

    if history.empty:
        return f"No price data available for {ticker} or {etf}."

    closes = history.get("Close", pd.DataFrame())
    lines = [
        f"# Sector Relative Performance: {ticker.upper()} vs {etf} ({sector_display})",
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| Period | Stock Return | ETF Return | Alpha |",
        "|--------|-------------|------------|-------|",
    ]

    stock_closes = closes.get(ticker.upper())
    etf_closes = closes.get(etf)

    for label, days_back in [("1-Week", 5), ("1-Month", 21), ("3-Month", 63), ("6-Month", 126)]:
        stock_return = (
            _safe_pct(stock_closes.dropna(), days_back) if stock_closes is not None else None
        )
        etf_return = _safe_pct(etf_closes.dropna(), days_back) if etf_closes is not None else None
        alpha = (
            stock_return - etf_return
            if stock_return is not None and etf_return is not None
            else None
        )
        lines.append(
            f"| {label} | {_fmt_pct(stock_return)} | {_fmt_pct(etf_return)} | {_fmt_pct(alpha)} |"
        )

    stock_ytd = _ytd_pct(stock_closes.dropna()) if stock_closes is not None else None
    etf_ytd = _ytd_pct(etf_closes.dropna()) if etf_closes is not None else None
    ytd_alpha = (
        stock_ytd - etf_ytd if stock_ytd is not None and etf_ytd is not None else None
    )
    lines.append(
        f"| YTD | {_fmt_pct(stock_ytd)} | {_fmt_pct(etf_ytd)} | {_fmt_pct(ytd_alpha)} |"
    )

    return "\n".join(lines)
