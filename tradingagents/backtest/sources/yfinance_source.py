"""yfinance ``PriceSource`` adapter. Supports DAILY only."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Set

import yfinance as yf

from tradingagents.backtest.prices import Bars, Resolution


class YFinanceSource:
    name = "yfinance"
    supports: Set[Resolution] = {Resolution.DAILY}

    def get_bars(
        self,
        ticker: str,
        start: date,
        end: date,
        resolution: Resolution,
    ) -> Bars:
        if resolution is not Resolution.DAILY:
            raise NotImplementedError(
                f"yfinance adapter supports only DAILY; got {resolution!r}. "
                "Register a Polygon or Alpha Vantage source for 1-min data."
            )

        # yfinance's history(end=...) is exclusive — add one day so the
        # caller's `end` is included.
        df = yf.Ticker(ticker).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
        )
        if df.empty or "Close" not in df.columns:
            raise RuntimeError(
                f"yfinance returned empty bars for {ticker} "
                f"{start}..{end}"
            )

        bars = [
            (idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx,
             float(close))
            for idx, close in zip(df.index, df["Close"])
        ]
        return Bars(
            ticker=ticker,
            resolution=Resolution.DAILY,
            bars=bars,
            source=self.name,
        )
