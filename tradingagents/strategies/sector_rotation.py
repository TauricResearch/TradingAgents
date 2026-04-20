"""Sector Momentum Rotation strategy signal (§4.1).

Computes relative sector strength by comparing the stock's sector ETF
performance against SPY over 1m/3m/6m windows. Signals whether the sector
is in leadership (overweight) or lagging (underweight).

Reference: Kakushadze & Serur §4.1 — "Sector Rotation"
"""

from __future__ import annotations

import yfinance as yf
import pandas as pd

from tradingagents.strategies.base import BaseStrategy, StrategySignal

# Map yfinance sector names to representative sector ETFs
SECTOR_ETFS: dict[str, str] = {
    "Technology": "XLK",
    "Communication Services": "XLC",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}

BENCHMARK = "SPY"


def _return(close: pd.Series, days: int) -> float | None:
    """Compute return over last N trading days, or None if insufficient data."""
    if len(close) < days + 1:
        return None
    return (close.iloc[-1] / close.iloc[-days - 1]) - 1


class SectorRotationStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Identifies whether the stock's sector is in favor — rising tide lifts all boats. Tips: Sector strength can mask individual stock weakness. Strongest signal when sector is top-3 or bottom-3 in relative strength. Combine with stock-specific signals for full picture."

    name = "sector_rotation"
    description = "Relative sector strength vs SPY (1m/3m/6m)"
    target_analysts = ["portfolio"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        # Determine sector
        info = kwargs.get("info")
        if info is None:
            try:
                info = yf.Ticker(ticker).info
            except Exception:
                info = {}

        sector = info.get("sector", "")
        etf_symbol = SECTOR_ETFS.get(sector, "")
        if not etf_symbol:
            return self._neutral(ticker, date, sector)

        # Fetch sector ETF + benchmark history (6 months)
        end = pd.Timestamp(date) + pd.DateOffset(days=1)
        start = pd.Timestamp(date) - pd.DateOffset(months=7)
        try:
            data = yf.download(
                [etf_symbol, BENCHMARK],
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False,
            )
            if data.empty:
                return self._neutral(ticker, date, sector)
            close = data["Close"]
        except Exception:
            return self._neutral(ticker, date, sector)

        if etf_symbol not in close.columns or BENCHMARK not in close.columns:
            return self._neutral(ticker, date, sector)

        sector_close = close[etf_symbol].dropna()
        bench_close = close[BENCHMARK].dropna()

        # Relative returns over 1m (22d), 3m (63d), 6m (126d)
        windows = {"1m": 22, "3m": 63, "6m": 126}
        relative: dict[str, float | None] = {}
        for label, days in windows.items():
            sr = _return(sector_close, days)
            br = _return(bench_close, days)
            if sr is not None and br is not None:
                relative[label] = sr - br
            else:
                relative[label] = None

        # Composite: weighted average of available windows (recent weighted more)
        weights = {"1m": 0.5, "3m": 0.3, "6m": 0.2}
        total_w = 0.0
        composite = 0.0
        for label, w in weights.items():
            if relative[label] is not None:
                composite += relative[label] * w
                total_w += w
        if total_w == 0:
            return self._neutral(ticker, date, sector)
        composite /= total_w

        # Signal strength
        if composite > 0.05:
            signal = "STRONG"
        elif composite > 0.01:
            signal = "MODERATE"
        elif composite > -0.01:
            signal = "WEAK"
        else:
            signal = "NEGATIVE"

        direction = "SUPPORTS" if composite > 0.01 else "CONTRADICTS" if composite < -0.01 else "NEUTRAL"

        # Build label
        parts = []
        for label in ("1m", "3m", "6m"):
            v = relative[label]
            if v is not None:
                parts.append(f"{label}: {v:+.1%}")
        rel_label = ", ".join(parts) if parts else "N/A"
        value_label = f"{sector} ({etf_symbol}) vs SPY: {composite:+.1%} composite [{rel_label}]"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(composite, 4),
            value_label=value_label,
            direction=direction,
            detail={
                "sector": sector,
                "etf": etf_symbol,
                "relative_1m": round(relative["1m"], 4) if relative["1m"] is not None else None,
                "relative_3m": round(relative["3m"], 4) if relative["3m"] is not None else None,
                "relative_6m": round(relative["6m"], 4) if relative["6m"] is not None else None,
                "composite": round(composite, 4),
            },
        )

    def _neutral(self, ticker: str, date: str, sector: str = "") -> StrategySignal:
        label = f"N/A (sector: {sector or 'unknown'})" if sector else "N/A (sector unknown)"
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0, value_label=label,
            direction="NEUTRAL", detail={"sector": sector},
        )
