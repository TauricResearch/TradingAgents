"""Shared fakes for Pro ingestion tests: no network, deterministic data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from tradingagents.contracts import OHLCVBar, Timeframe

BASE_TS = datetime(2026, 6, 1, tzinfo=timezone.utc)


class FakeTransport:
    """Routes get_json calls to canned payloads by URL substring."""

    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.calls: list[tuple[str, dict | None]] = []

    def get_json(self, url: str, params: dict | None = None):
        self.calls.append((url, params))
        for fragment, payload in self.routes.items():
            if fragment in url:
                return payload(params) if callable(payload) else payload
        raise AssertionError(f"unrouted URL in test: {url}")


def make_bars(
    n: int = 60, timeframe: Timeframe = Timeframe.D1, start_price: float = 100.0
) -> list[OHLCVBar]:
    """Deterministic gently-rising bars with valid OHLC geometry."""
    bars = []
    price = start_price
    for i in range(n):
        close = price + 0.5
        bars.append(
            OHLCVBar(
                timeframe=timeframe,
                start=BASE_TS + timedelta(days=i),
                open=price,
                high=max(price, close) + 1.0,
                low=min(price, close) - 1.0,
                close=close,
                volume=1000.0 + i,
            )
        )
        price = close
    return bars


def make_ohlcv_frame(n: int = 60, start_price: float = 100.0) -> pd.DataFrame:
    """DataFrame in the shape the base load_ohlcv returns (capitalized cols)."""
    rows = []
    price = start_price
    for i in range(n):
        close = price + 0.5
        rows.append(
            {
                "Date": (BASE_TS + timedelta(days=i)).date().isoformat(),
                "Open": price,
                "High": max(price, close) + 1.0,
                "Low": min(price, close) - 1.0,
                "Close": close,
                "Volume": 1000.0 + i,
            }
        )
        price = close
    return pd.DataFrame(rows)


class FakeBarsFeed:
    name = "fake_bars"

    def __init__(self, bars: list[OHLCVBar] | None = None):
        self.bars = bars if bars is not None else make_bars()

    def get_bars(self, symbol, timeframe, *, limit=250, end=None):
        return [b for b in self.bars if b.timeframe == timeframe][-limit:]
