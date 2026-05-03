"""China A-share data providers backed by optional Tushare and AKShare SDKs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .config import get_config
from .ticker_utils import (
    is_a_share_ticker,
    to_akshare_symbol,
    to_tushare_symbol,
)


class ChinaDataUnavailableError(Exception):
    """Raised when an optional China-market data source cannot provide data."""


def get_stock_tushare(symbol: str, start_date: str, end_date: str) -> str:
    """Retrieve A-share OHLCV data from Tushare daily quotes."""
    pro = _get_tushare_pro()
    ts_code = _require_a_share_tushare_symbol(symbol)
    try:
        df = pro.daily(
            ts_code=ts_code,
            start_date=_date_to_api(start_date),
            end_date=_date_to_api(end_date),
        )
    except Exception as exc:
        raise ChinaDataUnavailableError(f"Tushare daily request failed for {ts_code}: {exc}") from exc
    _save_raw_data(symbol, end_date, "tushare_get_stock", df)
    if df is None or df.empty:
        raise ChinaDataUnavailableError(f"Tushare returned no daily data for {ts_code}.")
    formatted = _format_tushare_daily(df)
    return _format_dataframe_report(
        formatted,
        title=f"China A-share stock data for {ts_code} from {start_date} to {end_date}",
        source="tushare",
    )


def get_stock_akshare(symbol: str, start_date: str, end_date: str) -> str:
    """Retrieve A-share OHLCV data from AKShare historical quotes."""
    ak = _import_optional("akshare", "pip install akshare")
    ak_symbol = _require_a_share_akshare_symbol(symbol)
    try:
        df = ak.stock_zh_a_hist(
            symbol=ak_symbol,
            period="daily",
            start_date=_date_to_api(start_date),
            end_date=_date_to_api(end_date),
            adjust=get_config().get("akshare_adjust", ""),
        )
    except Exception as exc:
        raise ChinaDataUnavailableError(
            f"AKShare historical request failed for {ak_symbol}: {exc}"
        ) from exc
    _save_raw_data(symbol, end_date, "akshare_get_stock", df)
    if df is None or df.empty:
        raise ChinaDataUnavailableError(f"AKShare returned no historical data for {ak_symbol}.")
    formatted = _format_akshare_daily(df)
    return _format_dataframe_report(
        formatted,
        title=f"China A-share stock data for {ak_symbol} from {start_date} to {end_date}",
        source="akshare",
    )


def get_fundamentals_tushare(ticker: str, curr_date: str = None) -> str:
    """Retrieve a compact A-share fundamentals snapshot from Tushare."""
    pro = _get_tushare_pro()
    ts_code = _require_a_share_tushare_symbol(ticker)
    curr_date = curr_date or datetime.now().strftime("%Y-%m-%d")
    end_date = _date_to_api(curr_date)
    start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y%m%d")

    sections = []
    stock_basic = _safe_tushare_call(lambda: pro.stock_basic(ts_code=ts_code))
    daily_basic = _safe_tushare_call(
        lambda: pro.daily_basic(ts_code=ts_code, start_date=start_date, end_date=end_date)
    )
    fina_indicator = _safe_tushare_call(
        lambda: pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=end_date)
    )

    _save_raw_data(
        ticker,
        curr_date,
        "tushare_get_fundamentals",
        {
            "stock_basic": _df_to_records(stock_basic),
            "daily_basic": _df_to_records(daily_basic),
            "fina_indicator": _df_to_records(fina_indicator),
        },
    )

    if stock_basic is not None and not stock_basic.empty:
        sections.append(_dataframe_head_markdown("Stock Basic", stock_basic))
    if daily_basic is not None and not daily_basic.empty:
        if "trade_date" in daily_basic.columns:
            daily_basic = daily_basic.sort_values("trade_date", ascending=False)
        sections.append(_dataframe_head_markdown("Daily Basic", daily_basic))
    if fina_indicator is not None and not fina_indicator.empty:
        if "end_date" in fina_indicator.columns:
            fina_indicator = fina_indicator.sort_values("end_date", ascending=False)
        sections.append(_dataframe_head_markdown("Financial Indicators", fina_indicator))

    if not sections:
        raise ChinaDataUnavailableError(f"Tushare returned no fundamentals data for {ts_code}.")

    return "\n\n".join(
        [
            f"# China A-share fundamentals for {ts_code}",
            f"# Source: tushare",
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            *sections,
        ]
    )


def get_fundamentals_akshare(ticker: str, curr_date: str = None) -> str:
    """Retrieve a compact A-share fundamentals snapshot from AKShare."""
    ak = _import_optional("akshare", "pip install akshare")
    ak_symbol = _require_a_share_akshare_symbol(ticker)
    sections = []

    individual_info = _safe_call(lambda: ak.stock_individual_info_em(symbol=ak_symbol))
    spot = _safe_call(lambda: ak.stock_zh_a_spot_em())

    matched_spot = None
    if isinstance(spot, pd.DataFrame) and not spot.empty and "代码" in spot.columns:
        matched_spot = spot[spot["代码"].astype(str).str.zfill(6) == ak_symbol]

    _save_raw_data(
        ticker,
        curr_date or datetime.now().strftime("%Y-%m-%d"),
        "akshare_get_fundamentals",
        {
            "stock_individual_info_em": _df_to_records(individual_info),
            "stock_zh_a_spot_em": _df_to_records(matched_spot),
        },
    )

    if isinstance(individual_info, pd.DataFrame) and not individual_info.empty:
        sections.append(_dataframe_head_markdown("Individual Info", individual_info))
    if isinstance(matched_spot, pd.DataFrame) and not matched_spot.empty:
        sections.append(_dataframe_head_markdown("Spot Snapshot", matched_spot))

    if not sections:
        raise ChinaDataUnavailableError(f"AKShare returned no fundamentals data for {ak_symbol}.")

    return "\n\n".join(
        [
            f"# China A-share fundamentals for {ak_symbol}",
            f"# Source: akshare",
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            *sections,
        ]
    )


def get_balance_sheet_tushare(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    return _get_tushare_statement(
        ticker,
        curr_date,
        method_name="balancesheet",
        title="Balance Sheet",
        raw_method="tushare_get_balance_sheet",
    )


def get_cashflow_tushare(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    return _get_tushare_statement(
        ticker,
        curr_date,
        method_name="cashflow",
        title="Cash Flow",
        raw_method="tushare_get_cashflow",
    )


def get_income_statement_tushare(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    return _get_tushare_statement(
        ticker,
        curr_date,
        method_name="income",
        title="Income Statement",
        raw_method="tushare_get_income_statement",
    )


def _get_tushare_statement(
    ticker: str,
    curr_date: str | None,
    *,
    method_name: str,
    title: str,
    raw_method: str,
) -> str:
    pro = _get_tushare_pro()
    ts_code = _require_a_share_tushare_symbol(ticker)
    curr_date = curr_date or datetime.now().strftime("%Y-%m-%d")
    end_date = _date_to_api(curr_date)
    start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=365 * 5)).strftime("%Y%m%d")
    method = getattr(pro, method_name)
    try:
        df = method(ts_code=ts_code, start_date=start_date, end_date=end_date)
    except Exception as exc:
        raise ChinaDataUnavailableError(
            f"Tushare {method_name} request failed for {ts_code}: {exc}"
        ) from exc
    _save_raw_data(ticker, curr_date, raw_method, df)
    if df is None or df.empty:
        raise ChinaDataUnavailableError(f"Tushare returned no {title.lower()} data for {ts_code}.")
    if "end_date" in df.columns:
        df = df.sort_values("end_date", ascending=False)
    return _format_dataframe_report(
        df,
        title=f"China A-share {title} data for {ts_code}",
        source="tushare",
    )


def _get_tushare_pro():
    token = os.getenv("TUSHARE_TOKEN") or os.getenv("TUSHARE_API_KEY")
    if not token:
        raise ChinaDataUnavailableError(
            "TUSHARE_TOKEN or TUSHARE_API_KEY environment variable is not set."
        )
    ts = _import_optional("tushare", "pip install tushare")
    return ts.pro_api(token)


def _import_optional(module_name: str, install_hint: str):
    try:
        return __import__(module_name)
    except ImportError as exc:
        raise ChinaDataUnavailableError(
            f"Optional dependency '{module_name}' is not installed. Install with `{install_hint}`."
        ) from exc


def _require_a_share_tushare_symbol(ticker: str) -> str:
    symbol = to_tushare_symbol(ticker)
    if not is_a_share_ticker(symbol):
        raise ChinaDataUnavailableError(f"{ticker} is not recognized as an A-share ticker.")
    return symbol


def _require_a_share_akshare_symbol(ticker: str) -> str:
    if not is_a_share_ticker(ticker):
        raise ChinaDataUnavailableError(f"{ticker} is not recognized as an A-share ticker.")
    return to_akshare_symbol(ticker)


def _format_tushare_daily(df: pd.DataFrame) -> pd.DataFrame:
    renamed = df.rename(
        columns={
            "trade_date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "pre_close": "Pre Close",
            "change": "Change",
            "pct_chg": "Pct Change",
            "vol": "Volume",
            "amount": "Amount",
        }
    ).copy()
    if "Date" in renamed.columns:
        renamed["Date"] = pd.to_datetime(renamed["Date"], format="%Y%m%d", errors="coerce")
        renamed = renamed.sort_values("Date")
        renamed["Date"] = renamed["Date"].dt.strftime("%Y-%m-%d")
    return renamed


def _format_akshare_daily(df: pd.DataFrame) -> pd.DataFrame:
    renamed = df.rename(
        columns={
            "日期": "Date",
            "开盘": "Open",
            "收盘": "Close",
            "最高": "High",
            "最低": "Low",
            "成交量": "Volume",
            "成交额": "Amount",
            "振幅": "Amplitude",
            "涨跌幅": "Pct Change",
            "涨跌额": "Change",
            "换手率": "Turnover",
        }
    ).copy()
    if "Date" in renamed.columns:
        renamed["Date"] = pd.to_datetime(renamed["Date"], errors="coerce")
        renamed = renamed.sort_values("Date")
        renamed["Date"] = renamed["Date"].dt.strftime("%Y-%m-%d")
    return renamed


def _format_dataframe_report(df: pd.DataFrame, *, title: str, source: str) -> str:
    if df is None or df.empty:
        raise ChinaDataUnavailableError(f"{source} returned no rows for {title}.")
    clean = df.copy()
    for col in clean.select_dtypes(include=["float", "float64"]).columns:
        clean[col] = clean[col].round(4)
    return "\n".join(
        [
            f"# {title}",
            f"# Source: {source}",
            f"# Total records: {len(clean)}",
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            clean.to_csv(index=False),
        ]
    )


def _date_to_api(date_value: str) -> str:
    return datetime.strptime(date_value, "%Y-%m-%d").strftime("%Y%m%d")


def _safe_tushare_call(func: Callable[[], pd.DataFrame]) -> pd.DataFrame | None:
    try:
        return func()
    except Exception:
        return None


def _safe_call(func: Callable[[], Any]) -> Any:
    try:
        return func()
    except Exception:
        return None


def _dataframe_head_markdown(title: str, df: pd.DataFrame, rows: int = 8) -> str:
    return f"## {title}\n\n```csv\n{df.head(rows).to_csv(index=False).strip()}\n```"


def _df_to_records(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    return value


def _save_raw_data(
    ticker: str,
    log_date: str,
    method: str,
    data: Any,
) -> None:
    cfg = get_config()
    results_dir = cfg.get("results_dir")
    if not results_dir:
        return
    safe_ticker = str(ticker).replace("/", "_")
    data_dir = Path(results_dir) / safe_ticker / str(log_date) / "data"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = data_dir / f"{method}_{timestamp}.json"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_df_to_records(data), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except OSError:
        return
