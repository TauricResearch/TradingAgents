# tradingagents/dataflows/akshare_stock.py
"""A-share (China) market data via AKShare.

Implements the same function signatures as y_finance.py so the existing
``VENDOR_METHODS`` routing infrastructure can dispatch to akshare when
the configured vendor is ``akshare``.

Symbol format: six-digit A-share code (e.g. "600519" for Kweichow Moutai,
"000001" for Ping An). The module auto-detects Shanghai (600xxx/601xxx/603xxx)
vs Shenzhen (000xxx/001xxx/002xxx/300xxx) exchanges.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

import akshare as ak
import pandas as pd

from .errors import NoMarketDataError

logger = logging.getLogger(__name__)

# ── A-share symbol normalization ──────────────────────────────────────────

_SH_A_PREFIXES = ("600", "601", "603", "605", "688")
_SZ_A_PREFIXES = ("000", "001", "002", "003", "300", "301")
_BJ_PREFIXES = ("8",)  # 83xxxx, 87xxxx etc. — Beijing Stock Exchange


def _normalize_a_share(raw: str) -> tuple[str, str]:
    """Return (code, exchange) for an A-share symbol.

    Accepts forms like "600519", "sh600519", "600519.SH", "000001.SZ",
    "688981", "838402". Raises ValueError for unrecognized formats.

    Exchanges: sh (Shanghai, incl. STAR Market 688xxx),
               sz (Shenzhen, incl. ChiNext 300xxx),
               bj (Beijing Stock Exchange 8xxxxx).
    """
    s = raw.strip().upper()
    # Strip exchange prefix/suffix
    for prefix in ("SH", "SZ", "BJ"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    for suffix in (".SH", ".SZ", ".BJ"):
        if s.endswith(suffix):
            s = s[:-3]
            break

    if not s.isdigit() or len(s) != 6:
        raise ValueError(
            f"'{raw}' is not a valid A-share code (expected 6 digits, got '{s}')"
        )

    if s.startswith(_SH_A_PREFIXES):
        return s, "sh"
    elif s.startswith(_SZ_A_PREFIXES):
        return s, "sz"
    elif s.startswith(_BJ_PREFIXES):
        return s, "bj"
    else:
        raise ValueError(
            f"'{raw}': unknown A-share prefix. "
            f"Shanghai: {_SH_A_PREFIXES}, "
            f"Shenzhen: {_SZ_A_PREFIXES}, "
            f"Beijing: 8xxxxx"
        )


# ── Stock price data (OHLCV) ─────────────────────────────────────────────


def get_stock_data(
    symbol: Annotated[str, "A-share stock code (e.g. '600519' or '000001')"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):
    """Fetch daily OHLCV data for an A-share stock via AKShare.

    Returns a CSV string with columns: date, open, high, low, close, volume.
    """
    code, exchange = _normalize_a_share(symbol)
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="qfq",  # 前复权
        )
    except Exception as e:
        raise NoMarketDataError(
            symbol, code, f"AKShare stock_zh_a_hist failed: {e}"
        ) from e

    if df is None or df.empty:
        raise NoMarketDataError(
            symbol, code, f"no OHLCV rows for {start_date} to {end_date}"
        )

    # AKShare returns Chinese column names → normalize to English
    col_map = {
        "日期": "date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
        "成交额": "amount",
        "振幅": "amplitude",
        "涨跌幅": "pct_change",
        "涨跌额": "change",
        "换手率": "turnover",
    }
    available = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=available)[list(available.values())]

    # Round price columns
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    header = f"# A-Share OHLCV data for {code} ({exchange.upper()})\n"
    header += f"# Period: {start_date} → {end_date}\n"
    header += f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + df.to_csv(index=False)


# ── Fundamentals ──────────────────────────────────────────────────────────


def get_fundamentals(
    ticker: Annotated[str, "A-share stock code"],
    curr_date: Annotated[str, "current date"] = None,
):
    """Get company fundamentals for an A-share stock via AKShare.

    Uses multiple fallback sources due to AKShare API instability
    across pandas versions. If the primary API fails, it tries
    alternative sources before returning a graceful degradation.
    """
    code, exchange = _normalize_a_share(ticker)
    header = f"# Company Fundamentals for {code} ({exchange.upper()})\n"
    header += f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    # Strategy 1: stock_individual_info_em (Eastmoney — most comprehensive)
    try:
        info_df = ak.stock_individual_info_em(symbol=code)
        if info_df is not None and not info_df.empty:
            # stock_individual_info_em returns ["item", "value"]
            # but some pandas versions cause column mismatch — handle defensively
            if len(info_df.columns) >= 2:
                col_0, col_1 = info_df.columns[0], info_df.columns[1]
                info = dict(zip(info_df[col_0], info_df[col_1]))
            elif "item" in info_df.columns and "value" in info_df.columns:
                info = dict(zip(info_df["item"], info_df["value"]))
            else:
                raise NoMarketDataError(ticker, code, "unexpected column format")

            lines = []
            for key in info:
                val = info[key]
                if val is not None and str(val) not in ("", "--", "nan", "None"):
                    lines.append(f"{key}: {val}")
            if lines:
                return header + "\n".join(lines)
    except Exception:
        logger.debug("stock_individual_info_em failed for %s, trying fallback", code)

    # Strategy 2: stock_zh_a_spot_em — realtime spot data (limited fields)
    try:
        spot_df = ak.stock_zh_a_spot_em()
        row = spot_df[spot_df["代码"] == code]
        if not row.empty:
            r = row.iloc[0]
            lines = []
            field_map = {
                "名称": "Name", "最新价": "Latest Price", "涨跌幅": "Change %",
                "成交量": "Volume", "成交额": "Amount", "换手率": "Turnover Rate",
                "市盈率-动态": "PE (TTM)", "市净率": "PB",
            }
            for cn, en in field_map.items():
                if cn in r.index and pd.notna(r[cn]) and r[cn] != "-":
                    lines.append(f"{en}: {r[cn]}")
            if lines:
                disclaimer = (
                    "# Note: Full fundamentals unavailable via current AKShare API.\n"
                    "# Showing realtime market snapshot instead.\n\n"
                )
                return header + disclaimer + "\n".join(lines)
    except Exception:
        logger.debug("stock_zh_a_spot_em fallback also failed for %s", code)

    # Strategy 3: stock_info_a_code_name — absolute minimum (name only)
    try:
        name_df = ak.stock_info_a_code_name()
        row = name_df[name_df["code"] == code]
        if not row.empty:
            r = row.iloc[0]
            return header + f"Name: {r['name']}\n# Note: Full fundamental data unavailable via current AKShare API version."
    except Exception:
        pass

    raise NoMarketDataError(
        ticker, code,
        "all fundamental data sources failed (stock_individual_info_em, "
        "stock_zh_a_spot_em, stock_info_a_code_name). "
        "The AKShare API may have version-specific incompatibilities."
    )


# ── Financial statements ──────────────────────────────────────────────────


def _get_financial_data(code: str, report_type: str, freq: str, curr_date: str | None = None) -> pd.DataFrame:
    """Fetch financial data from AKShare (Eastmoney source).

    report_type: "balance_sheet", "income_statement", "cash_flow"
    freq: "annual" or "quarterly"
    curr_date: if provided, exclude reports dated after this date
               (prevents lookahead bias in historical backtesting).
    """
    indicator_map = {
        "balance_sheet": "按年度",
        "income_statement": "按报告期",
        "cash_flow": "按报告期",
    }
    indicator = indicator_map[report_type]

    try:
        df = ak.stock_financial_abstract_ths(symbol=code, indicator=indicator)
    except Exception as e:
        raise NoMarketDataError(code, code, f"{report_type} data failed: {e}") from e

    if df is None or df.empty:
        raise NoMarketDataError(code, code, f"no {report_type} data")

    date_col = df.columns[0]

    # Filter by frequency
    if freq == "annual":
        df = df[df[date_col].astype(str).str.contains("-12-31")]

    # Filter by curr_date — exclude future reports (prevent lookahead bias)
    if curr_date is not None:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        cutoff = pd.to_datetime(curr_date)
        df = df[df[date_col] <= cutoff]

    return df


def get_balance_sheet(
    ticker: Annotated[str, "A-share stock code"],
    freq: Annotated[str, "annual or quarterly"] = "annual",
    curr_date: Annotated[str, "YYYY-MM-DD"] = None,
):
    """Get balance sheet data for an A-share stock."""
    code, exchange = _normalize_a_share(ticker)
    data = _get_financial_data(code, "balance_sheet", freq, curr_date)

    csv_str = data.to_csv(index=False)
    header = f"# Balance Sheet for {code} ({exchange.upper()}, {freq})\n"
    header += f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_str


def get_cashflow(
    ticker: Annotated[str, "A-share stock code"],
    freq: Annotated[str, "annual or quarterly"] = "annual",
    curr_date: Annotated[str, "YYYY-MM-DD"] = None,
):
    """Get cash flow data for an A-share stock."""
    code, exchange = _normalize_a_share(ticker)
    data = _get_financial_data(code, "cash_flow", freq, curr_date)

    csv_str = data.to_csv(index=False)
    header = f"# Cash Flow for {code} ({exchange.upper()}, {freq})\n"
    header += f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_str


def get_income_statement(
    ticker: Annotated[str, "A-share stock code"],
    freq: Annotated[str, "annual or quarterly"] = "annual",
    curr_date: Annotated[str, "YYYY-MM-DD"] = None,
):
    """Get income statement data for an A-share stock."""
    code, exchange = _normalize_a_share(ticker)
    data = _get_financial_data(code, "income_statement", freq, curr_date)

    csv_str = data.to_csv(index=False)
    header = f"# Income Statement for {code} ({exchange.upper()}, {freq})\n"
    header += f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_str


# ── Insider transactions (not applicable for A-shares via akshare) ────────


def get_insider_transactions(
    ticker: Annotated[str, "A-share stock code"],
):
    """Insider transactions are not available via AKShare free tier."""
    code, _ = _normalize_a_share(ticker)
    return (
        f"Insider transaction data is not available for A-share stock '{code}' "
        f"via the free AKShare API. This data is published by the SSE/SZSE "
        f"and accessible through paid data vendors."
    )
