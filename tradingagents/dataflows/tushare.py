from __future__ import annotations

import os
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Callable

import pandas as pd
from stockstats import wrap

from .exceptions import DataVendorUnavailable


_SUPPORTED_EXCHANGES = {"SH", "SZ", "BJ", "HK"}
_SUFFIX_MAP = {
    "SH": "SH",
    "SS": "SH",
    "SSE": "SH",
    "SZ": "SZ",
    "SZSE": "SZ",
    "BJ": "BJ",
    "BSE": "BJ",
    "HK": "HK",
    "HKG": "HK",
    "SEHK": "HK",
}

_A_SHARE_EXCHANGES = {"SH", "SZ", "BJ"}


def _parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


def _to_api_date(date_str: str) -> str:
    return _parse_date(date_str).strftime("%Y%m%d")


def _classify_market(ts_code: str) -> str:
    if "." in ts_code:
        suffix = ts_code.rsplit(".", 1)[1]
        if suffix in _A_SHARE_EXCHANGES:
            return "a_share"
        if suffix == "HK":
            return "hk"
    return "us"


def _normalize_ts_code(symbol: str) -> str:
    raw = symbol.strip().upper()

    if "." in raw:
        code, suffix = raw.split(".", 1)
        suffix = _SUFFIX_MAP.get(suffix, suffix)
        if suffix in _A_SHARE_EXCHANGES and code.isdigit():
            return f"{code.zfill(6)}.{suffix}"
        if suffix == "HK" and code.isdigit():
            return f"{code.zfill(5)}.HK"
        raise DataVendorUnavailable(
            f"Tushare currently supports A-share, Hong Kong, and US tickers only, got '{symbol}'."
        )

    if raw.isdigit() and len(raw) <= 6:
        code = raw.zfill(6)
        if code.startswith(("6", "9", "5")):
            return f"{code}.SH"
        if code.startswith(("0", "2", "3")):
            return f"{code}.SZ"
        if code.startswith(("4", "8")):
            return f"{code}.BJ"
        return f"{raw.zfill(5)}.HK"

    if raw.replace("-", "").isalnum():
        return raw

    raise DataVendorUnavailable(
        f"Cannot map ticker '{symbol}' to a supported Tushare market automatically."
    )


@lru_cache(maxsize=1)
def _get_pro_client():
    token = (
        os.getenv("TUSHARE_TOKEN")
        or os.getenv("TUSHARE_API_TOKEN")
        or os.getenv("TS_TOKEN")
    )
    if not token:
        raise DataVendorUnavailable(
            "TUSHARE_TOKEN is not set. Configure token or use fallback vendor."
        )

    try:
        import tushare as ts
    except ImportError as exc:
        raise DataVendorUnavailable(
            "tushare package is not installed. Install it to enable tushare vendor."
        ) from exc

    try:
        ts.set_token(token)
        return ts.pro_api(token)
    except Exception as exc:
        raise DataVendorUnavailable(f"Failed to initialize tushare client: {exc}") from exc


def _to_csv_with_header(df: pd.DataFrame, title: str) -> str:
    if df is None or df.empty:
        return f"No {title.lower()} data found."

    header = f"# {title}\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + df.to_csv(index=False)


def _filter_statement(df: pd.DataFrame, freq: str, curr_date: str | None) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    output = df.copy()

    if curr_date and "end_date" in output.columns:
        cutoff = _to_api_date(curr_date)
        output = output[output["end_date"].astype(str) <= cutoff]

    if freq.lower() == "annual" and "end_date" in output.columns:
        output = output[output["end_date"].astype(str).str.endswith("1231")]

    sort_col = "end_date" if "end_date" in output.columns else output.columns[0]
    output = output.sort_values(sort_col, ascending=False).head(8)
    return output


def _fetch_price_data(pro, ts_code: str, start_api: str, end_api: str) -> pd.DataFrame:
    market = _classify_market(ts_code)
    if market == "a_share":
        return pro.daily(ts_code=ts_code, start_date=start_api, end_date=end_api)
    if market == "hk":
        return pro.hk_daily(ts_code=ts_code, start_date=start_api, end_date=end_api)
    return pro.us_daily(ts_code=ts_code, start_date=start_api, end_date=end_api)


def get_stock(symbol: str, start_date: str, end_date: str) -> str:
    pro = _get_pro_client()
    ts_code = _normalize_ts_code(symbol)

    start_api = _to_api_date(start_date)
    end_api = _to_api_date(end_date)

    data = _fetch_price_data(pro, ts_code, start_api, end_api)
    if data is None or data.empty:
        return f"No stock data found for '{ts_code}' between {start_date} and {end_date}."

    rename_map = {
        "trade_date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "vol": "Volume",
        "amount": "Amount",
        "pct_chg": "PctChg",
        "pre_close": "PrevClose",
        "change": "Change",
    }

    output = data.rename(columns=rename_map)
    if "Date" in output.columns:
        output["Date"] = pd.to_datetime(output["Date"], format="%Y%m%d").dt.strftime(
            "%Y-%m-%d"
        )
    output = output.sort_values("Date", ascending=True)

    preferred_cols = [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "PrevClose",
        "Change",
        "PctChg",
        "Volume",
        "Amount",
    ]
    existing_cols = [c for c in preferred_cols if c in output.columns]
    output = output[existing_cols]

    return _to_csv_with_header(
        output,
        f"Tushare stock data for {ts_code} from {start_date} to {end_date}",
    )


def _load_price_frame(symbol: str, curr_date: str, look_back_days: int = 260) -> pd.DataFrame:
    pro = _get_pro_client()
    ts_code = _normalize_ts_code(symbol)
    end_dt = _parse_date(curr_date)
    start_dt = end_dt - timedelta(days=look_back_days)
    data = _fetch_price_data(
        pro,
        ts_code,
        start_dt.strftime("%Y%m%d"),
        end_dt.strftime("%Y%m%d"),
    )
    if data is None or data.empty:
        raise DataVendorUnavailable(
            f"No tushare price data found for '{ts_code}' before {curr_date}."
        )

    df = data.rename(
        columns={
            "trade_date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "vol": "Volume",
        }
    ).copy()
    df["Date"] = pd.to_datetime(df["Date"], format="%Y%m%d")
    df = df.sort_values("Date", ascending=True)
    return df[["Date", "Open", "High", "Low", "Close", "Volume"]]


def get_indicator(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
) -> str:
    descriptions = {
        "close_50_sma": "50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.",
        "close_200_sma": "200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.",
        "close_10_ema": "10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.",
        "macd": "MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.",
        "macds": "MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.",
        "macdh": "MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.",
        "rsi": "RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.",
        "boll": "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.",
        "boll_ub": "Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.",
        "boll_lb": "Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.",
        "atr": "ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.",
        "vwma": "VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.",
        "mfi": "MFI: Uses both price and volume to measure buying and selling pressure. Usage: Identify overbought (>80) or oversold (<20) conditions and confirm trends or reversals.",
    }
    if indicator not in descriptions:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(descriptions.keys())}"
        )

    current_dt = _parse_date(curr_date)
    start_dt = current_dt - timedelta(days=look_back_days)
    stats_df = wrap(_load_price_frame(symbol, curr_date))
    stats_df["Date"] = stats_df["Date"].dt.strftime("%Y-%m-%d")
    stats_df[indicator]

    lines = []
    probe_dt = current_dt
    while probe_dt >= start_dt:
        date_str = probe_dt.strftime("%Y-%m-%d")
        row = stats_df[stats_df["Date"] == date_str]
        if row.empty:
            lines.append(f"{date_str}: N/A: Not a trading day (weekend or holiday)")
        else:
            value = row.iloc[0][indicator]
            if pd.isna(value):
                lines.append(f"{date_str}: N/A")
            else:
                lines.append(f"{date_str}: {value}")
        probe_dt -= timedelta(days=1)

    return (
        f"## {indicator} values from {start_dt.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + "\n".join(lines)
        + "\n\n"
        + descriptions[indicator]
    )


def get_fundamentals(ticker: str, curr_date: str | None = None) -> str:
    pro = _get_pro_client()
    ts_code = _normalize_ts_code(ticker)
    market = _classify_market(ts_code)

    if curr_date:
        curr_dt = _parse_date(curr_date)
    else:
        curr_dt = datetime.now()
        curr_date = curr_dt.strftime("%Y-%m-%d")

    end_api = curr_dt.strftime("%Y%m%d")
    start_api_40d = (curr_dt - timedelta(days=40)).strftime("%Y%m%d")
    start_api_400d = (curr_dt - timedelta(days=400)).strftime("%Y%m%d")

    if market == "a_share":
        basic = pro.stock_basic(
            ts_code=ts_code,
            fields="ts_code,symbol,name,area,industry,market,list_date,list_status",
        )
        latest_price = pro.daily_basic(
            ts_code=ts_code,
            start_date=start_api_40d,
            end_date=end_api,
        )
        fina_indicator = pro.fina_indicator(
            ts_code=ts_code,
            start_date=start_api_400d,
            end_date=end_api,
        )
    elif market == "hk":
        basic = pro.hk_basic(ts_code=ts_code)
        latest_price = pro.hk_daily(ts_code=ts_code, start_date=start_api_40d, end_date=end_api)
        fina_indicator = None
    else:
        basic = pro.us_basic(ts_code=ts_code)
        latest_price = pro.us_daily(ts_code=ts_code, start_date=start_api_40d, end_date=end_api)
        fina_indicator = None

    lines = [
        f"Ticker: {ts_code}",
        f"Market: {market}",
        f"Reference date: {curr_date}",
    ]

    if basic is not None and not basic.empty:
        row = basic.iloc[0]
        if market == "a_share":
            field_map = {
                "name": "Name",
                "area": "Area",
                "industry": "Industry",
                "market": "Market",
                "list_date": "List Date",
                "list_status": "List Status",
            }
        elif market == "hk":
            field_map = {
                "name": "Name",
                "fullname": "Full Name",
                "enname": "English Name",
                "market": "Market",
                "curr_type": "Currency",
                "list_date": "List Date",
                "list_status": "List Status",
            }
        else:
            field_map = {
                "name": "Name",
                "enname": "English Name",
                "classify": "Classify",
                "list_date": "List Date",
                "delist_date": "Delist Date",
            }
        for field, label in field_map.items():
            value = row.get(field)
            if pd.notna(value):
                lines.append(f"{label}: {value}")

    if latest_price is not None and not latest_price.empty:
        row = latest_price.sort_values("trade_date", ascending=False).iloc[0]
        if market == "a_share":
            field_map = {
                "trade_date": "Latest Trade Date",
                "close": "Close",
                "turnover_rate": "Turnover Rate",
                "pe": "PE",
                "pb": "PB",
                "ps": "PS",
                "dv_ratio": "Dividend Yield Ratio",
                "total_mv": "Total Market Value",
                "circ_mv": "Circulating Market Value",
            }
        else:
            field_map = {
                "trade_date": "Latest Trade Date",
                "close": "Close",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "pre_close": "Prev Close",
                "change": "Change",
                "pct_chg": "Pct Change",
                "vol": "Volume",
                "amount": "Amount",
            }
        for field, label in field_map.items():
            value = row.get(field)
            if pd.notna(value):
                lines.append(f"{label}: {value}")

    if fina_indicator is not None and not fina_indicator.empty:
        row = fina_indicator.sort_values("end_date", ascending=False).iloc[0]
        field_map = {
            "end_date": "Latest Financial Period",
            "roe": "ROE",
            "roa": "ROA",
            "grossprofit_margin": "Gross Margin",
            "netprofit_margin": "Net Margin",
            "debt_to_assets": "Debt to Assets",
            "ocf_to_or": "OCF to Revenue",
        }
        for field, label in field_map.items():
            value = row.get(field)
            if pd.notna(value):
                lines.append(f"{label}: {value}")
    elif market == "hk":
        income = pro.hk_income(ts_code=ts_code, end_date=end_api)
        if income is not None and not income.empty:
            latest_end = income["end_date"].astype(str).max()
            lines.append(f"Latest Financial Period: {latest_end}")
            sample = income[income["end_date"].astype(str) == latest_end].head(12)
            for _, rec in sample.iterrows():
                lines.append(f"{rec.get('ind_name')}: {rec.get('ind_value')}")
    else:
        income = pro.us_income(ts_code=ts_code, end_date=end_api)
        if income is not None and not income.empty:
            latest_end = income["end_date"].astype(str).max()
            lines.append(f"Latest Financial Period: {latest_end}")
            sample = income[income["end_date"].astype(str) == latest_end].head(12)
            for _, rec in sample.iterrows():
                lines.append(f"{rec.get('ind_name')}: {rec.get('ind_value')}")

    header = f"# Tushare fundamentals for {ts_code}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + "\n".join(lines)


def _statement_common(
    ticker: str,
    freq: str,
    curr_date: str | None,
    fetcher: Callable,
    title: str,
) -> str:
    pro = _get_pro_client()
    ts_code = _normalize_ts_code(ticker)
    market = _classify_market(ts_code)
    data = fetcher(pro, ts_code, market)
    filtered = _filter_statement(data, freq, curr_date)
    return _to_csv_with_header(filtered, f"Tushare {title} for {ts_code} ({freq})")


def get_balance_sheet(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
) -> str:
    return _statement_common(
        ticker,
        freq,
        curr_date,
        lambda pro, ts_code, market: (
            pro.balancesheet(ts_code=ts_code)
            if market == "a_share"
            else pro.hk_balancesheet(ts_code=ts_code)
            if market == "hk"
            else pro.us_balancesheet(ts_code=ts_code)
        ),
        "balance sheet",
    )


def get_cashflow(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
) -> str:
    return _statement_common(
        ticker,
        freq,
        curr_date,
        lambda pro, ts_code, market: (
            pro.cashflow(ts_code=ts_code)
            if market == "a_share"
            else pro.hk_cashflow(ts_code=ts_code)
            if market == "hk"
            else pro.us_cashflow(ts_code=ts_code)
        ),
        "cashflow",
    )


def get_income_statement(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
) -> str:
    return _statement_common(
        ticker,
        freq,
        curr_date,
        lambda pro, ts_code, market: (
            pro.income(ts_code=ts_code)
            if market == "a_share"
            else pro.hk_income(ts_code=ts_code)
            if market == "hk"
            else pro.us_income(ts_code=ts_code)
        ),
        "income statement",
    )


def get_insider_transactions(ticker: str) -> str:
    pro = _get_pro_client()
    ts_code = _normalize_ts_code(ticker)
    market = _classify_market(ts_code)

    if market != "a_share":
        raise DataVendorUnavailable(
            f"Tushare insider transactions currently support A-share tickers only, got '{ts_code}'."
        )

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=365)

    try:
        data = pro.stk_holdertrade(
            ts_code=ts_code,
            start_date=start_dt.strftime("%Y%m%d"),
            end_date=end_dt.strftime("%Y%m%d"),
        )
    except Exception as exc:
        raise DataVendorUnavailable(
            f"Failed to retrieve tushare insider transactions for '{ts_code}': {exc}"
        ) from exc

    if data is None or data.empty:
        return f"No tushare insider transactions found for '{ts_code}'."

    output = data.rename(
        columns={
            "ann_date": "AnnouncementDate",
            "holder_name": "HolderName",
            "holder_type": "HolderType",
            "in_de": "Direction",
            "change_vol": "ChangeVolume",
            "change_ratio": "ChangeRatio",
            "after_share": "AfterShareholding",
            "after_ratio": "AfterRatio",
            "avg_price": "AveragePrice",
            "total_share": "TotalShareholding",
            "begin_date": "StartDate",
            "close_date": "EndDate",
        }
    ).copy()

    for col in ("AnnouncementDate", "StartDate", "EndDate"):
        if col in output.columns:
            output[col] = pd.to_datetime(
                output[col], format="%Y%m%d", errors="coerce"
            ).dt.strftime("%Y-%m-%d")

    preferred_cols = [
        "AnnouncementDate",
        "HolderName",
        "HolderType",
        "Direction",
        "ChangeVolume",
        "ChangeRatio",
        "AfterShareholding",
        "AfterRatio",
        "AveragePrice",
        "TotalShareholding",
        "StartDate",
        "EndDate",
    ]
    existing_cols = [col for col in preferred_cols if col in output.columns]
    if existing_cols:
        output = output[existing_cols]

    sort_col = "AnnouncementDate" if "AnnouncementDate" in output.columns else output.columns[0]
    output = output.sort_values(sort_col, ascending=False)
    return _to_csv_with_header(output, f"Tushare insider transactions for {ts_code}")
