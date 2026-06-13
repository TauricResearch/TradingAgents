from __future__ import annotations

from datetime import datetime, timedelta
from io import StringIO
from typing import Annotated

import pandas as pd

from .akshare_http import run_akshare
from .symbol_utils import NoMarketDataError


def _ak():
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError(
            "AKShare is not installed. Install it in the tradingagents environment "
            "with: pip install akshare"
        ) from exc
    return ak


def _digits(symbol: str) -> str:
    raw = str(symbol).strip().upper()
    if "." in raw:
        raw = raw.split(".", 1)[0]
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) != 6:
        raise NoMarketDataError(symbol, raw, "A-share symbols must contain 6 digits")
    return digits


def _sina_symbol(symbol: str) -> str:
    code = _digits(symbol)
    prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
    return f"{prefix}{code}"


def _compact_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%Y%m%d")


def _normalise_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "日期": "Date",
        "date": "Date",
        "开盘": "Open",
        "open": "Open",
        "最高": "High",
        "high": "High",
        "最低": "Low",
        "low": "Low",
        "收盘": "Close",
        "close": "Close",
        "成交量": "Volume",
        "volume": "Volume",
        "成交额": "Turnover",
        "amount": "Turnover",
        "换手率": "TurnoverRate",
        "turnover": "TurnoverRate",
        "涨跌幅": "PctChange",
        "pct_chg": "PctChange",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    if "Volume" not in df.columns:
        df["Volume"] = 0
    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"AKShare OHLCV response missing columns: {missing}")
    df = df[required + [c for c in ("Turnover", "TurnoverRate", "PctChange") if c in df.columns]]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for col in ["Open", "High", "Low", "Close", "Volume", "Turnover", "TurnoverRate", "PctChange"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Date", "Close"]).sort_values("Date")
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    return df


def _filter_date_range(df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    dates = pd.to_datetime(df["Date"], errors="coerce")
    return df[(dates >= start) & (dates <= end)].copy()


def _load_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    ak = _ak()
    code = _digits(symbol)
    tx_symbol = _sina_symbol(symbol)
    compact_start = _compact_date(start_date)
    compact_end = _compact_date(end_date)
    errors: list[str] = []

    sources = (
        (
            "stock_zh_a_hist",
            lambda: run_akshare(
                ak.stock_zh_a_hist,
                symbol=code,
                period="daily",
                start_date=compact_start,
                end_date=compact_end,
                adjust="qfq",
            ),
        ),
        (
            "stock_zh_a_hist_tx",
            lambda: run_akshare(
                ak.stock_zh_a_hist_tx,
                symbol=tx_symbol,
                start_date=compact_start,
                end_date=compact_end,
                adjust="qfq",
            ),
        ),
        (
            "stock_zh_a_daily",
            lambda: run_akshare(
                ak.stock_zh_a_daily,
                symbol=tx_symbol,
                start_date=compact_start,
                end_date=compact_end,
                adjust="qfq",
            ),
        ),
    )

    for source_name, loader in sources:
        try:
            data = loader()
            if data is None or data.empty:
                errors.append(f"{source_name}: empty response")
                continue
            normalised = _normalise_ohlcv(data)
            filtered = _filter_date_range(normalised, start_date, end_date)
            if filtered.empty:
                errors.append(f"{source_name}: no rows in requested date range")
                continue
            return filtered
        except Exception as exc:  # noqa: BLE001 - collect and try next vendor API
            errors.append(f"{source_name}: {type(exc).__name__}: {exc}")

    detail = "; ".join(errors) if errors else "all sources failed"
    raise NoMarketDataError(
        symbol,
        code,
        f"no A-share rows between {start_date} and {end_date} ({detail})",
    )


def get_stock_data(
    symbol: Annotated[str, "A-share ticker symbol, e.g. 600519.SH or 000001.SZ"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):
    df = _load_ohlcv(symbol, start_date, end_date)
    code = _digits(symbol)
    header = f"# A-share stock data for {code} from {start_date} to {end_date}\n"
    header += "# Source: AKShare (eastmoney/tencent/sina fallback), qfq adjusted\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + df.to_csv(index=False)


def get_indicator(
    symbol: Annotated[str, "A-share ticker symbol"],
    indicator: Annotated[str, "technical indicator"],
    curr_date: Annotated[str, "Current trading date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    from stockstats import wrap

    supported = {
        "close_50_sma", "close_200_sma", "close_10_ema",
        "macd", "macds", "macdh", "rsi",
        "boll", "boll_ub", "boll_lb", "atr", "vwma", "mfi",
    }
    if indicator not in supported:
        raise ValueError(f"Indicator {indicator} is not supported. Please choose from: {sorted(supported)}")

    curr = datetime.strptime(curr_date, "%Y-%m-%d")
    start = curr - timedelta(days=max(int(look_back_days), 30) + 260)
    df = _load_ohlcv(symbol, start.strftime("%Y-%m-%d"), curr_date)
    stock_df = wrap(df.copy())
    stock_df[indicator]
    stock_df["Date"] = pd.to_datetime(stock_df["Date"]).dt.strftime("%Y-%m-%d")
    cutoff = (curr - timedelta(days=int(look_back_days))).strftime("%Y-%m-%d")
    recent = stock_df[stock_df["Date"] >= cutoff]

    lines = []
    for _, row in recent.iterrows():
        value = row.get(indicator)
        rendered = "N/A" if pd.isna(value) else str(value)
        lines.append(f"{row['Date']}: {rendered}")

    return (
        f"## {indicator} values from {cutoff} to {curr_date}\n\n"
        + "\n".join(lines)
        + "\n\nSource: AKShare OHLCV with local stockstats calculation."
    )


def get_fundamentals(
    ticker: Annotated[str, "A-share ticker symbol"],
    curr_date: Annotated[str, "current date"] = None,
):
    ak = _ak()
    code = _digits(ticker)
    try:
        df = run_akshare(ak.stock_individual_info_em, symbol=code)
    except Exception as exc:
        return f"A-share fundamentals unavailable from AKShare for {ticker}: {type(exc).__name__}: {exc}"
    if df is None or df.empty:
        raise NoMarketDataError(ticker, code, "no AKShare individual info")
    return (
        f"# A-share company fundamentals for {code}\n"
        "# Source: AKShare stock_individual_info_em\n\n"
        + df.to_csv(index=False)
    )


def _financial_report(ticker: str, symbol: str, label: str) -> str:
    ak = _ak()
    sina = _sina_symbol(ticker)
    try:
        df = run_akshare(ak.stock_financial_report_sina, stock=sina, symbol=symbol)
    except Exception as exc:
        return f"{label} unavailable from AKShare for {ticker}: {type(exc).__name__}: {exc}"
    if df is None or df.empty:
        return f"{label} unavailable from AKShare for {ticker}: empty response"
    return f"# {label} for {ticker}\n# Source: AKShare stock_financial_report_sina\n\n" + df.to_csv(index=False)


def get_balance_sheet(ticker, freq: str = "quarterly", curr_date: str = None):
    return _financial_report(ticker, "资产负债表", "Balance sheet")


def get_cashflow(ticker, freq: str = "quarterly", curr_date: str = None):
    return _financial_report(ticker, "现金流量表", "Cash flow statement")


def get_income_statement(ticker, freq: str = "quarterly", curr_date: str = None):
    return _financial_report(ticker, "利润表", "Income statement")


def get_news(ticker, start_date, end_date):
    ak = _ak()
    code = _digits(ticker)
    try:
        df = run_akshare(ak.stock_news_em, symbol=code)
    except Exception as exc:
        return f"A-share news unavailable from AKShare for {ticker}: {type(exc).__name__}: {exc}"
    if df is None or df.empty:
        return f"No A-share news found for {ticker} from AKShare."

    date_cols = [c for c in df.columns if "时间" in str(c) or "日期" in str(c) or "time" in str(c).lower()]
    if date_cols:
        col = date_cols[0]
        dates = pd.to_datetime(df[col], errors="coerce")
        mask = (dates >= pd.to_datetime(start_date)) & (dates <= pd.to_datetime(end_date) + pd.Timedelta(days=1))
        df = df[mask.fillna(False)]
    df = df.head(20)
    return (
        f"# A-share company news for {code} from {start_date} to {end_date}\n"
        "# Source: AKShare stock_news_em (Eastmoney)\n\n"
        + df.to_csv(index=False)
    )


def get_global_news(curr_date, look_back_days: int = 7, limit: int = 50):
    ak = _ak()
    candidates = (
        ("stock_info_global_cls", {"symbol": "全部"}),
        ("stock_info_global_ths", {}),
        ("stock_info_cjzc_em", {}),
    )
    errors = []
    for name, kwargs in candidates:
        func = getattr(ak, name, None)
        if func is None:
            continue
        try:
            df = run_akshare(func, **kwargs)
            if df is not None and not df.empty:
                return (
                    f"# China A-share relevant market news as of {curr_date}\n"
                    f"# Source: AKShare {name}\n\n"
                    + df.head(int(limit or 50)).to_csv(index=False)
                )
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    return "China market news unavailable from AKShare. " + "; ".join(errors)


def get_insider_transactions(ticker):
    return "Insider transaction data is not configured for A-shares in akshare_cn."


def parse_stock_data_csv(text: str) -> pd.DataFrame:
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    if not lines:
        raise ValueError("No CSV rows found in stock data output.")
    return pd.read_csv(StringIO("\n".join(lines)))
