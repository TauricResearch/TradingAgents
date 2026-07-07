"""Gold-complex feeds built on the base framework's yfinance layer.

Daily bars come through the existing cached OHLCV loader
(dataflows.stockstats_utils.load_ohlcv), which already normalizes broker
symbols (XAUUSD -> GC=F) and enforces staleness/lookahead guards. The
loader is injectable so tests and backtests supply frames directly.

Cross-asset context (silver correlation, DXY, US10Y) is derived
deterministically from the same daily closes.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timezone

import pandas as pd

from tradingagents.contracts import MetricReading, OHLCVBar, Timeframe
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.pro.ingestion.derived import pearson_correlation

OhlcvLoader = Callable[[str, str], pd.DataFrame]


def _default_loader(symbol: str, curr_date: str) -> pd.DataFrame:
    from tradingagents.dataflows.stockstats_utils import load_ohlcv

    return load_ohlcv(symbol, curr_date)


def _frame_to_bars(frame: pd.DataFrame, symbol: str, limit: int) -> list[OHLCVBar]:
    if frame is None or frame.empty:
        raise NoMarketDataError(symbol, detail="empty OHLCV frame")
    frame = frame.tail(limit)
    bars = []
    for _, row in frame.iterrows():
        day = pd.Timestamp(row["Date"]).date() if "Date" in row else pd.Timestamp(row.name).date()
        bars.append(
            OHLCVBar(
                timeframe=Timeframe.D1,
                start=datetime.combine(day, time.min, tzinfo=timezone.utc),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume", 0.0)),
            )
        )
    return bars


class YFinanceDailyBarsFeed:
    """Daily bars for any symbol the base loader understands (GC=F, SI=F,
    DX-Y.NYB, ^TNX, GLD, ...). Daily timeframe only — the upstream loader
    has no intraday support (see the data-source decision table)."""

    name = "yfinance_daily"

    def __init__(self, loader: OhlcvLoader | None = None, as_of: date | None = None):
        self._loader = loader or _default_loader
        self._as_of = as_of

    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        limit: int = 250,
        end: datetime | None = None,
    ) -> list[OHLCVBar]:
        if timeframe is not Timeframe.D1:
            raise ValueError(f"{self.name} supports daily bars only, got {timeframe.value}")
        curr = end.date() if end else (self._as_of or datetime.now(timezone.utc).date())
        frame = self._loader(symbol, curr.isoformat())
        return _frame_to_bars(frame, symbol, limit)


class GoldCrossAssetFeed:
    """Derived gold-complex context: silver correlation, DXY, 10Y yield.

    All values are computed in code from daily closes; window length is a
    constructor parameter so backtests can align it with their horizon.
    """

    name = "gold_cross_asset"

    DXY_SYMBOL = "DX-Y.NYB"
    TNX_SYMBOL = "^TNX"  # CBOE 10Y index = yield * 10
    SILVER_SYMBOL = "SI=F"
    GOLD_SYMBOL = "GC=F"

    def __init__(self, bars_feed: YFinanceDailyBarsFeed, correlation_window: int = 30):
        if correlation_window < 3:
            raise ValueError("correlation_window must be >= 3")
        self._bars = bars_feed
        self._window = correlation_window

    def _closes(self, symbol: str, limit: int) -> list[float]:
        return [b.close for b in self._bars.get_bars(symbol, Timeframe.D1, limit=limit)]

    def get_metrics(self) -> list[MetricReading]:
        as_of = datetime.now(timezone.utc)
        gold = self._closes(self.GOLD_SYMBOL, self._window)
        silver = self._closes(self.SILVER_SYMBOL, self._window)
        n = min(len(gold), len(silver))
        readings = [
            MetricReading(
                name=f"XAU_XAG_CORR_{self._window}D",
                value=pearson_correlation(gold[-n:], silver[-n:]),
                unit="correlation",
                as_of=as_of,
                source=self.name,
            )
        ]
        dxy = self._closes(self.DXY_SYMBOL, 1)
        readings.append(
            MetricReading(
                name="DXY", value=dxy[-1], unit="index", as_of=as_of, source=self.name
            )
        )
        tnx = self._closes(self.TNX_SYMBOL, 1)
        readings.append(
            MetricReading(
                name="US10Y",
                value=tnx[-1] / 10.0,  # ^TNX quotes yield x10 (42.5 => 4.25%)
                unit="percent",
                as_of=as_of,
                source=self.name,
            )
        )
        return readings
