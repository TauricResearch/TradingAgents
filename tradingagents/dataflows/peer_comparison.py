"""Sector and peer relative performance comparison using yfinance."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import yfinance as yf
import pandas as pd


# ---------------------------------------------------------------------------
# Reuse sector/ETF mappings from alpha_vantage_scanner to stay DRY
# ---------------------------------------------------------------------------

# Sector key (lowercase-dashes) → SPDR ETF
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

# Representative large-cap peers per sector (same as alpha_vantage_scanner)
_SECTOR_TICKERS: dict[str, list[str]] = {
    "technology": ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "ADBE", "CRM", "AMD", "INTC"],
    "healthcare": ["UNH", "JNJ", "LLY", "PFE", "ABT", "MRK", "TMO", "ABBV", "DHR", "AMGN"],
    "financials": ["JPM", "BAC", "WFC", "GS", "MS", "BLK", "SCHW", "AXP", "C", "USB"],
    "energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HES"],
    "consumer-discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "TJX", "BKNG", "CMG"],
    "consumer-staples": ["PG", "KO", "PEP", "COST", "WMT", "PM", "MDLZ", "CL", "KHC", "GIS"],
    "industrials": ["CAT", "HON", "UNP", "UPS", "BA", "RTX", "DE", "LMT", "GE", "MMM"],
    "materials": ["LIN", "APD", "SHW", "ECL", "FCX", "NEM", "NUE", "DOW", "DD", "PPG"],
    "real-estate": ["PLD", "AMT", "CCI", "EQIX", "SPG", "PSA", "O", "WELL", "DLR", "AVB"],
    "utilities": ["NEE", "DUK", "SO", "D", "AEP", "SRE", "EXC", "XEL", "WEC", "ED"],
    "communication-services": ["META", "GOOGL", "NFLX", "DIS", "CMCSA", "T", "VZ", "CHTR", "TMUS", "EA"],
}

# Yahoo Finance sector string → normalised key
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _fmt_pct(val: Optional[float]) -> str:
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_sector_peers(ticker: str) -> tuple[str, str, list[str]]:
    """
    Identify a ticker's sector and return peer tickers.

    Returns:
        (sector_display_name, sector_key, peer_tickers)
        sector_key is lowercase-dashed (e.g. "technology")
        If sector cannot be identified, returns ("Unknown", "", [])
    """
    try:
        info = yf.Ticker(ticker.upper()).info
        raw_sector = info.get("sector", "")
        sector_key = _SECTOR_NORMALISE.get(raw_sector, raw_sector.lower().replace(" ", "-"))
        peers = _SECTOR_TICKERS.get(sector_key, [])
        # Exclude the ticker itself from peers
        peers = [p for p in peers if p.upper() != ticker.upper()]
        return raw_sector or "Unknown", sector_key, peers
    except Exception:
        return "Unknown", "", []


def compute_relative_performance(
    ticker: str,
    sector_key: str,
    peers: list[str],
) -> str:
    """
    Compare ticker's returns vs peers and sector ETF over multiple horizons.

    Args:
        ticker: The stock being analysed
        sector_key: Normalised sector key (lowercase-dashes)
        peers: List of peer ticker symbols

    Returns:
        Formatted Markdown report with ranked performance table.
    """
    etf = _SECTOR_ETFS.get(sector_key)

    # Build list of all symbols to download (max 8 peers + ticker + ETF)
    all_symbols = [ticker.upper()] + peers[:8]
    if etf and etf not in all_symbols:
        all_symbols.append(etf)

    try:
        hist = yf.download(
            all_symbols,
            period="6mo",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        return f"Error downloading price data for peer comparison: {e}"

    if hist.empty:
        return "No price data available for peer comparison."

    # Extract closing prices
    if len(all_symbols) > 1:
        closes_raw = hist.get("Close", pd.DataFrame())
    else:
        closes_raw = hist.get("Close", pd.Series()).to_frame(name=all_symbols[0])

    rows = []
    for sym in all_symbols:
        try:
            if sym in closes_raw.columns:
                s = closes_raw[sym].dropna()
            else:
                continue
            if s.empty:
                continue
            w1 = _safe_pct(s, 5)
            m1 = _safe_pct(s, 21)
            m3 = _safe_pct(s, 63)
            m6 = _safe_pct(s, 126)
            ytd = _ytd_pct(s)
            rows.append({
                "symbol": sym,
                "1W": w1, "1M": m1, "3M": m3, "6M": m6, "YTD": ytd,
                "is_target": sym.upper() == ticker.upper(),
                "is_etf": sym == etf,
            })
        except Exception:
            continue

    if not rows:
        return "Unable to compute returns — no price data retrieved."

    # Sort by 3-month return (descending) for ranking
    rows.sort(key=lambda r: r["3M"] if r["3M"] is not None else float("-inf"), reverse=True)

    # Determine ticker rank
    target_rank = next(
        (i + 1 for i, r in enumerate(rows) if r["is_target"]), None
    )
    n_peers = sum(1 for r in rows if not r["is_etf"])

    header = [
        f"# Relative Performance Analysis: {ticker.upper()}",
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Sector: {sector_key.replace('-', ' ').title()} | Peer rank (3M): {target_rank}/{n_peers}",
        "",
        "| Symbol | Role | 1-Week | 1-Month | 3-Month | 6-Month | YTD |",
        "|--------|------|--------|---------|---------|---------|-----|",
    ]

    table_rows = []
    for r in rows:
        role = "► TARGET" if r["is_target"] else ("ETF Benchmark" if r["is_etf"] else "Peer")
        table_rows.append(
            f"| {r['symbol']} | {role} "
            f"| {_fmt_pct(r['1W'])} "
            f"| {_fmt_pct(r['1M'])} "
            f"| {_fmt_pct(r['3M'])} "
            f"| {_fmt_pct(r['6M'])} "
            f"| {_fmt_pct(r['YTD'])} |"
        )

    # Alpha vs ETF
    target_row = next((r for r in rows if r["is_target"]), None)
    etf_row = next((r for r in rows if r["is_etf"]), None)
    alpha_lines = []
    if target_row and etf_row:
        alpha_lines.append("")
        alpha_lines.append("## Alpha vs Sector ETF")
        alpha_lines.append("")
        for period, tk, bm in [
            ("1-Month", target_row["1M"], etf_row["1M"]),
            ("3-Month", target_row["3M"], etf_row["3M"]),
            ("6-Month", target_row["6M"], etf_row["6M"]),
        ]:
            if tk is not None and bm is not None:
                alpha = tk - bm
                alpha_lines.append(f"- **{period}**: {_fmt_pct(tk)} vs ETF {_fmt_pct(bm)} → Alpha {_fmt_pct(alpha)}")
            else:
                alpha_lines.append(f"- **{period}**: N/A")

    return "\n".join(header + table_rows + alpha_lines)


def get_peer_comparison_report(ticker: str, curr_date: str = None) -> str:
    """
    Full peer comparison report for a ticker.

    Args:
        ticker: Stock ticker symbol
        curr_date: Current trading date (informational only)

    Returns:
        Formatted Markdown report
    """
    sector_display, sector_key, peers = get_sector_peers(ticker)

    if not peers:
        return (
            f"# Peer Comparison: {ticker.upper()}\n\n"
            f"Could not identify sector peers for {ticker}. "
            f"Sector detected: '{sector_display}'"
        )

    return compute_relative_performance(ticker, sector_key, peers)


def get_sector_relative_report(ticker: str, curr_date: str = None) -> str:
    """
    Focused sector-vs-ticker comparison (ETF benchmark focus).

    Args:
        ticker: Stock ticker symbol
        curr_date: Current trading date (informational only)

    Returns:
        Formatted Markdown report comparing ticker vs sector ETF only.
    """
    sector_display, sector_key, _ = get_sector_peers(ticker)
    etf = _SECTOR_ETFS.get(sector_key)

    if not etf:
        return (
            f"# Sector Relative Performance: {ticker.upper()}\n\n"
            f"No ETF benchmark found for sector '{sector_display}'."
        )

    try:
        symbols = [ticker.upper(), etf]
        hist = yf.download(
            symbols,
            period="6mo",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        return f"Error downloading data for {ticker} vs {etf}: {e}"

    if hist.empty:
        return f"No price data available for {ticker} or {etf}."

    closes = hist.get("Close", pd.DataFrame())

    lines = [
        f"# Sector Relative Performance: {ticker.upper()} vs {etf} ({sector_display})",
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| Period | Stock Return | ETF Return | Alpha |",
        "|--------|-------------|------------|-------|",
    ]

    for period_label, days_back in [("1-Week", 5), ("1-Month", 21), ("3-Month", 63), ("6-Month", 126)]:
        tk_ret = etf_ret = None
        for sym, col_type in [(ticker.upper(), "stock"), (etf, "etf")]:
            if sym in closes.columns:
                s = closes[sym].dropna()
                pct = _safe_pct(s, days_back)
                if col_type == "stock":
                    tk_ret = pct
                else:
                    etf_ret = pct

        alpha = (tk_ret - etf_ret) if tk_ret is not None and etf_ret is not None else None
        lines.append(
            f"| {period_label} | {_fmt_pct(tk_ret)} | {_fmt_pct(etf_ret)} | {_fmt_pct(alpha)} |"
        )

    # YTD
    tk_ytd = etf_ytd = None
    for sym, col_type in [(ticker.upper(), "stock"), (etf, "etf")]:
        if sym in closes.columns:
            s = closes[sym].dropna()
            pct = _ytd_pct(s)
            if col_type == "stock":
                tk_ytd = pct
            else:
                etf_ytd = pct

    ytd_alpha = (tk_ytd - etf_ytd) if tk_ytd is not None and etf_ytd is not None else None
    lines.append(f"| YTD | {_fmt_pct(tk_ytd)} | {_fmt_pct(etf_ytd)} | {_fmt_pct(ytd_alpha)} |")

    return "\n".join(lines)
