"""Pydantic models for Binance REST API parameters and responses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class KlineInterval(str, Enum):
    """Valid kline/candlestick intervals for the Binance API."""

    ONE_MINUTE = "1m"
    THREE_MINUTES = "3m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    TWO_HOURS = "2h"
    FOUR_HOURS = "4h"
    SIX_HOURS = "6h"
    EIGHT_HOURS = "8h"
    TWELVE_HOURS = "12h"
    ONE_DAY = "1d"
    THREE_DAYS = "3d"
    ONE_WEEK = "1w"
    ONE_MONTH = "1M"


@dataclass(frozen=True)
class KlineParams:
    """Parameters for GET /api/v3/klines.

    Reference: https://api.binance.com/api/v3/klines
    """

    symbol: str
    interval: KlineInterval
    start_time: Optional[int] = None   # Unix ms
    end_time: Optional[int] = None     # Unix ms
    time_zone: str = "0"               # UTC offset, e.g. "0", "+08:00"
    limit: int = 200                   # Max 1000


@dataclass(frozen=True)
class TickerParams:
    """Parameters for GET /api/v3/ticker/price or /api/v3/ticker/24hr.

    Reference: https://api.binance.com/api/v3/ticker/
    """

    symbol: str
    ticker_type: str = "FULL"  # "FULL" or "MINI"


@dataclass(frozen=True)
class DepthParams:
    """Parameters for GET /api/v3/depth.

    Reference: https://api.binance.com/api/v3/depth
    """

    symbol: str
    limit: int = 100  # Valid: 1, 5, 10, 20, 50, 100, 500, 1000, 5000


@dataclass
class Kline:
    """A single candlestick returned by /api/v3/klines."""

    open_time: int          # Unix ms
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int         # Unix ms
    quote_asset_volume: float
    number_of_trades: int
    taker_buy_base_volume: float
    taker_buy_quote_volume: float

    @classmethod
    def from_raw(cls, raw: list) -> "Kline":
        """Parse one element from the klines array response."""
        return cls(
            open_time=int(raw[0]),
            open=float(raw[1]),
            high=float(raw[2]),
            low=float(raw[3]),
            close=float(raw[4]),
            volume=float(raw[5]),
            close_time=int(raw[6]),
            quote_asset_volume=float(raw[7]),
            number_of_trades=int(raw[8]),
            taker_buy_base_volume=float(raw[9]),
            taker_buy_quote_volume=float(raw[10]),
        )
