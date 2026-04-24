"""Standalone market-price client for geopolitical scanner tools."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd
import requests

from .finnhub_common import ThirdPartyTimeoutError
from .stockstats_utils import YFinanceError, safe_yf_download

logger = logging.getLogger(__name__)


_MARKET_PRICE_SYMBOLS = {
    "Gold": "GC=F",
    "WTI Crude": "CL=F",
    "Brent Crude": "BZ=F",
    "Bitcoin": "BTC-USD",
    "EUR/USD": "EURUSD=X",
    "JPY/USD": "JPYUSD=X",
    "CNY/USD": "CNYUSD=X",
}


@dataclass(frozen=True)
class MarketPriceRow:
    asset: str
    symbol: str
    current_price: float
    absolute_change: float
    percent_change: float


class MarketPricesClient:
    """Fetch live gold, oil, bitcoin, and currency prices from yfinance."""

    def fetch_rows(self) -> dict[str, MarketPriceRow]:
        symbols = list(_MARKET_PRICE_SYMBOLS.values())
        try:
            # period="5d" to ensure we have enough data for prev_close calculation
            # even across weekends or low-volume assets.
            prices_df = safe_yf_download(
                symbols,
                period="5d",
                auto_adjust=False,
                progress=False,
            )
        except requests.exceptions.Timeout as exc:
            raise ThirdPartyTimeoutError("Request timed out fetching market prices") from exc
        except ThirdPartyTimeoutError:
            raise
        except Exception as exc:
            raise YFinanceError(f"Failed to fetch market prices: {exc}") from exc

        rows: dict[str, MarketPriceRow] = {}
        for asset, symbol in _MARKET_PRICE_SYMBOLS.items():
            closes = self._extract_latest_closes(prices_df, symbol)
            if closes is None:
                logger.warning("Insufficient price history for %s (%s); skipping asset.", asset, symbol)
                continue

            current_price = float(closes.iloc[-1])
            prev_close = float(closes.iloc[-2])
            absolute_change = current_price - prev_close
            percent_change = (absolute_change / prev_close * 100) if prev_close else 0.0

            rows[asset] = MarketPriceRow(
                asset=asset,
                symbol=symbol,
                current_price=current_price,
                absolute_change=absolute_change,
                percent_change=percent_change,
            )

        return rows

    @staticmethod
    def _extract_latest_closes(download_df: pd.DataFrame, symbol: str) -> list[float] | None:
        if download_df is None or getattr(download_df, "empty", True):
            return None

        # yfinance can return a Series for single symbol or a DataFrame for multiple symbols.
        # Multi-symbol case with multi-index columns: download_df["Close"] is a DataFrame.
        # Single-symbol case: download_df["Close"] is usually a Series.
        
        try:
            close_col = download_df["Close"]
            if isinstance(close_col, pd.DataFrame):
                # Multi-symbol
                if symbol not in close_col.columns:
                    return None
                closes = close_col[symbol].dropna()
            else:
                # Single-symbol Series
                closes = close_col.dropna()
        except Exception:
            return None

        if len(closes) < 2:
            return None
        return closes


def _format_market_price_table(title: str, rows: list[MarketPriceRow]) -> str:
    lines = [
        title,
        f"_Data retrieved on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "| Asset | Symbol | Current Price | Change | Change % |",
        "|---|---|---:|---:|---:|",
    ]
    for row in rows:
        price_str = f"${row.current_price:,.2f}"
        change_str = f"{row.absolute_change:+.2f}"
        pct_str = f"{row.percent_change:+.2f}%"
        lines.append(f"| {row.asset} | {row.symbol} | {price_str} | {change_str} | {pct_str} |")
    return "\n".join(lines)


def get_gold_price_snapshot() -> str:
    client = MarketPricesClient()
    rows = client.fetch_rows()
    return _format_market_price_table("# Gold Price Snapshot", [rows["Gold"]])


def get_oil_prices_snapshot() -> str:
    client = MarketPricesClient()
    rows = client.fetch_rows()
    return _format_market_price_table(
        "# Oil Price Snapshot",
        [rows["WTI Crude"], rows["Brent Crude"]],
    )


def get_bitcoin_price_snapshot() -> str:
    client = MarketPricesClient()
    rows = client.fetch_rows()
    return _format_market_price_table("# Bitcoin Price Snapshot", [rows["Bitcoin"]])


def get_eur_usd_rate_snapshot() -> str:
    """Snapshot of EUR/USD FX rate."""
    client = MarketPricesClient()
    rows = client.fetch_rows()
    return _format_market_price_table("# EUR/USD Exchange Rate", [rows["EUR/USD"]])


def get_jpy_usd_rate_snapshot() -> str:
    """Snapshot of JPY/USD FX rate."""
    client = MarketPricesClient()
    rows = client.fetch_rows()
    return _format_market_price_table("# JPY/USD Exchange Rate", [rows["JPY/USD"]])


def get_cny_usd_rate_snapshot() -> str:
    """Snapshot of CNY/USD FX rate (Yuan/USD)."""
    client = MarketPricesClient()
    rows = client.fetch_rows()
    return _format_market_price_table("# CNY/USD Exchange Rate", [rows["CNY/USD"]])
