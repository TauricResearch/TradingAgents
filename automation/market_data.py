from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

import pandas as pd
import yfinance as yf


@dataclass(frozen=True)
class DataSymbol:
    requested: str
    data_symbol: str
    display_name: str


def configure_yfinance_cache(path: Path) -> None:
    """Keep yfinance's sqlite timezone cache inside the repo workspace."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(path))
    except Exception:
        pass


def resolve_data_symbol(ticker: str, aliases: dict | None = None) -> DataSymbol:
    aliases = aliases or {}
    entry = aliases.get(ticker, {})
    if isinstance(entry, str):
        return DataSymbol(requested=ticker, data_symbol=entry, display_name=ticker)
    return DataSymbol(
        requested=ticker,
        data_symbol=entry.get("data_symbol", ticker),
        display_name=entry.get("display_name", ticker),
    )


def has_price_data(symbol: str, *, period: str = "3mo") -> tuple[bool, str]:
    """Return whether yfinance has usable recent OHLCV data for symbol."""
    try:
        history = yf.Ticker(symbol).history(period=period, auto_adjust=False)
    except Exception as exc:
        return False, f"yfinance error for {symbol}: {type(exc).__name__}: {exc}"
    if history is None or history.empty:
        return False, f"No yfinance price data for {symbol} over {period}."
    required = {"Open", "High", "Low", "Close"}
    missing = sorted(required.difference(history.columns))
    if missing:
        return False, f"yfinance data for {symbol} missing columns: {', '.join(missing)}."
    return True, f"{len(history)} recent rows available for {symbol}."


def fetch_daily_close_history(symbol: str, *, period: str = "6mo", max_points: int = 120) -> list[dict]:
    """Fetch recent daily close data for PDF charting."""
    try:
        history = yf.Ticker(symbol).history(period=period, auto_adjust=False)
    except Exception:
        history = None
    if history is None or history.empty or "Close" not in history.columns:
        history = _load_cached_history(symbol)
    if history is None or history.empty or "Close" not in history.columns:
        return []
    history = history.dropna(subset=["Close"]).tail(max_points)
    points: list[dict] = []
    for idx, row in history.iterrows():
        points.append(
            {
                "date": idx.strftime("%Y-%m-%d"),
                "close": float(row["Close"]),
            }
        )
    return points


def _load_cached_history(symbol: str):
    cache_dir = Path(os.getenv("TRADINGAGENTS_CACHE_DIR", Path.home() / ".tradingagents" / "cache"))
    files = sorted(
        cache_dir.glob(f"{symbol}-YFin-data-*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return None
    data = pd.read_csv(files[0], encoding="utf-8")
    if "Date" not in data.columns or "Close" not in data.columns:
        return None
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data["Close"] = pd.to_numeric(data["Close"], errors="coerce")
    data = data.dropna(subset=["Date", "Close"]).set_index("Date")
    return data
