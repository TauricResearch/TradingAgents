"""Range-stats compute + formatters for open/close/volume vs 52w/6m/3m/1m ranges.

Pure-ish module. The only side effect is the historical-data fetch which goes
through the configured vendor (`route_to_vendor("get_stock_data", ...)`).
Three formatters live alongside (markdown for the LLM tool; dict for the WebUI
card; compact block for Telegram), all sharing the dict shape `compute_range_stats`
produces.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from io import StringIO
from typing import Optional

import pandas as pd

from tradingagents.dataflows.interface import route_to_vendor


WINDOWS_TRADING_DAYS = {"52w": 252, "6m": 126, "3m": 63, "1m": 21}


class RangeStatsUnavailable(Exception):
    """Raised when no historical data is available for the symbol."""


def _load_ohlcv(symbol: str, trade_date: str) -> pd.DataFrame:
    """Fetch ~380 calendar days of OHLCV ending at trade_date.

    Returns a DataFrame with columns Date (YYYY-MM-DD str), Open, High, Low,
    Close, Volume. Empty DataFrame on failure.
    """
    end_dt = datetime.strptime(trade_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=400)
    csv_text = route_to_vendor(
        "get_stock_data",
        symbol,
        start_dt.strftime("%Y-%m-%d"),
        end_dt.strftime("%Y-%m-%d"),
    )
    # Vendor outputs include header comment lines starting with '#'.
    if not isinstance(csv_text, str) or "No data" in csv_text:
        return pd.DataFrame()
    try:
        df = pd.read_csv(StringIO(csv_text), comment="#")
    except Exception:
        return pd.DataFrame()
    if df.empty or "Date" not in df.columns:
        return pd.DataFrame()
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df = df.sort_values("Date").reset_index(drop=True)
    return df


def _window_low_high(df: pd.DataFrame, n: int, col: str) -> tuple[Optional[float], Optional[float]]:
    """Return (low, high) over the last n trading days inclusive of today.

    Returns (None, None) if fewer than n rows available.
    """
    if len(df) < n:
        return None, None
    sl = df.tail(n)
    return float(sl[col].min()), float(sl[col].max())


def _calc_metrics(current: float, low: Optional[float], high: Optional[float]) -> dict:
    if low is None or high is None:
        return {"low": None, "high": None,
                "pct_above_low": None, "pct_below_high": None, "position_pct": None}
    if low == 0:
        pct_above_low = None
    else:
        pct_above_low = (current - low) / low * 100.0
    if high == 0:
        pct_below_high = None
    else:
        # Negative when current < high (the typical case). Formatters render
        # this signed (e.g. "-10.8%" = 10.8% below the recent high).
        pct_below_high = (current - high) / high * 100.0
    if high == low:
        position_pct = 50.0
    else:
        position_pct = (current - low) / (high - low) * 100.0
    return {
        "low": low,
        "high": high,
        "pct_above_low": pct_above_low,
        "pct_below_high": pct_below_high,
        "position_pct": position_pct,
    }


def compute_range_stats(symbol: str, trade_date: str) -> dict:
    """Compute range stats for one (symbol, trade_date).

    Returns a dict of shape:
        {
            "symbol": str,
            "trade_date": str,
            "today": {"effective_date": str, "open": float, "close": float, "volume": int},
            "metrics": {
                "open":   {"52w": {...}, "6m": {...}, "3m": {...}, "1m": {...}},
                "close":  {...},
                "volume": {...},
            },
        }
    where each window dict has keys: low, high, pct_above_low, pct_below_high, position_pct.
    None values mean "n/a" (insufficient history or degenerate divisor).

    Raises RangeStatsUnavailable when no data could be fetched at all.
    """
    df = _load_ohlcv(symbol, trade_date)
    if df.empty:
        raise RangeStatsUnavailable(f"No OHLCV data for {symbol} up to {trade_date}")

    # If trade_date is a non-trading day, use the most recent row.
    today_rows = df[df["Date"] <= trade_date]
    if today_rows.empty:
        raise RangeStatsUnavailable(f"No rows on or before {trade_date} for {symbol}")
    today_row = today_rows.iloc[-1]
    effective_date = today_row["Date"]

    today = {
        "effective_date": effective_date,
        "open": float(today_row["Open"]),
        "close": float(today_row["Close"]),
        "volume": int(today_row["Volume"]),
    }

    # Trim to rows up through effective_date (drop rows after, defensive)
    df_eff = df[df["Date"] <= effective_date].reset_index(drop=True)

    metrics: dict = {"open": {}, "close": {}, "volume": {}}
    for label, n in WINDOWS_TRADING_DAYS.items():
        for metric_name, col in (("open", "Open"), ("close", "Close"), ("volume", "Volume")):
            low, high = _window_low_high(df_eff, n, col)
            metrics[metric_name][label] = _calc_metrics(today[metric_name], low, high)

    return {
        "symbol": symbol,
        "trade_date": trade_date,
        "today": today,
        "metrics": metrics,
    }


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    return f"{v:+.1f}%"


def _fmt_pos(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    return f"{v:.1f}%"


def _fmt_price(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    return f"{v:.2f}"


def _fmt_vol_short(v: int | float) -> str:
    """Render a volume as 1.2K / 58.2M / 1.4B."""
    v = float(v)
    if abs(v) >= 1e9:
        return f"{v / 1e9:.1f}B"
    if abs(v) >= 1e6:
        return f"{v / 1e6:.1f}M"
    if abs(v) >= 1e3:
        return f"{v / 1e3:.1f}K"
    return f"{v:.0f}"


def _color_for_window(window: dict) -> Optional[str]:
    """Return 'red' near recent high, 'green' near recent low, else None."""
    pos = window.get("position_pct")
    if pos is None:
        return None
    if pos >= 80.0:
        return "red"
    if pos <= 20.0:
        return "green"
    return None


def _table_for_metric(label: str, current: float, windows: dict, *, is_volume: bool = False) -> str:
    fmt = _fmt_vol_short if is_volume else _fmt_price
    cur_str = f"{int(current):,}" if is_volume else f"{current:.2f}"
    lines = [
        f"## {label.title()} ({cur_str}) vs historical ranges",
        "| Window | Low    | High   | vs Low   | vs High  | Position |",
        "|--------|--------|--------|----------|----------|----------|",
    ]
    for w in ("52w", "6m", "3m", "1m"):
        d = windows[w]
        lo_raw = fmt(d["low"]) if d["low"] is not None else "n/a"
        hi_raw = fmt(d["high"]) if d["high"] is not None else "n/a"
        lines.append(
            "| {w:<6} | {lo:<6} | {hi:<6} | {al:<8} | {bh:<8} | {pos:<8} |".format(
                w=w,
                lo=lo_raw,
                hi=hi_raw,
                al=_fmt_pct(d["pct_above_low"]),
                bh=_fmt_pct(d["pct_below_high"]),
                pos=_fmt_pos(d["position_pct"]),
            )
        )
    return "\n".join(lines)


def format_range_stats_markdown(stats: dict) -> str:
    """LLM-facing + Telegram-fallback markdown render."""
    today = stats["today"]
    parts = [
        f"# Range Stats for {stats['symbol']} on {stats['trade_date']}",
        f"Today: open={today['open']:.2f}  close={today['close']:.2f}  "
        f"volume={today['volume']:,}  (effective_date={today['effective_date']})",
        "",
        _table_for_metric("Close",  today["close"],  stats["metrics"]["close"]),
        "",
        _table_for_metric("Open",   today["open"],   stats["metrics"]["open"]),
        "",
        _table_for_metric("Volume", today["volume"], stats["metrics"]["volume"], is_volume=True),
    ]
    return "\n".join(parts)


def format_range_stats_for_webui(stats: dict) -> dict:
    """Returns a payload streamlit can render directly: numbers + color hints."""
    out = {
        "symbol": stats["symbol"],
        "trade_date": stats["trade_date"],
        "today": stats["today"],
        "metrics": {},
    }
    for metric, windows in stats["metrics"].items():
        out["metrics"][metric] = {
            w: {**d, "color": _color_for_window(d)} for w, d in windows.items()
        }
    return out


def format_range_stats_telegram(stats: dict) -> str:
    """Compact 4-line block: header + close, open, volume rows showing 52w and 1m."""
    sym = stats["symbol"]
    date = stats["trade_date"]
    today = stats["today"]

    def row(label: str, cur: str, windows: dict) -> str:
        w52 = windows["52w"]
        w1m = windows["1m"]
        return (
            f"{label:<5} {cur:<10} → "
            f"52w {_fmt_pct(w52['pct_above_low'])}/{_fmt_pct(w52['pct_below_high'])} "
            f"({_fmt_pos(w52['position_pct'])})  "
            f"1m {_fmt_pct(w1m['pct_above_low'])}/{_fmt_pct(w1m['pct_below_high'])} "
            f"({_fmt_pos(w1m['position_pct'])})"
        )

    return "\n".join([
        f"📊 Range Stats ({sym}, {date})",
        row("Close", f"{today['close']:.2f}", stats["metrics"]["close"]),
        row("Open",  f"{today['open']:.2f}",  stats["metrics"]["open"]),
        row("Vol",   _fmt_vol_short(today["volume"]), stats["metrics"]["volume"]),
    ])
