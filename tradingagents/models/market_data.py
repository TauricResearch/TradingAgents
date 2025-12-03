from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class OHLCVBar(BaseModel):
    timestamp: datetime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: int = Field(ge=0)
    adjusted_close: Optional[Decimal] = Field(default=None, gt=0)

    @field_validator("high")
    @classmethod
    def high_gte_low(cls, v: Decimal, info) -> Decimal:
        if "low" in info.data and v < info.data["low"]:
            raise ValueError("high must be >= low")
        return v

    @field_validator("high")
    @classmethod
    def high_gte_open_close(cls, v: Decimal, info) -> Decimal:
        if "open" in info.data and v < info.data["open"]:
            raise ValueError("high must be >= open")
        if "close" in info.data and v < info.data["close"]:
            raise ValueError("high must be >= close")
        return v

    @field_validator("low")
    @classmethod
    def low_lte_open_close(cls, v: Decimal, info) -> Decimal:
        if "open" in info.data and v > info.data["open"]:
            raise ValueError("low must be <= open")
        if "close" in info.data and v > info.data["close"]:
            raise ValueError("low must be <= close")
        return v


class OHLCV(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    bars: list[OHLCVBar] = Field(default_factory=list)
    interval: str = Field(default="1d")
    currency: str = Field(default="USD")

    @property
    def start_date(self) -> Optional[datetime]:
        return self.bars[0].timestamp if self.bars else None

    @property
    def end_date(self) -> Optional[datetime]:
        return self.bars[-1].timestamp if self.bars else None

    def get_bar(self, dt: datetime) -> Optional[OHLCVBar]:
        for bar in self.bars:
            if bar.timestamp.date() == dt.date():
                return bar
        return None

    def slice(self, start: datetime, end: datetime) -> "OHLCV":
        filtered = [b for b in self.bars if start <= b.timestamp <= end]
        return OHLCV(
            ticker=self.ticker,
            bars=filtered,
            interval=self.interval,
            currency=self.currency,
        )


class TechnicalIndicators(BaseModel):
    timestamp: datetime
    ticker: str

    sma_20: Optional[Decimal] = None
    sma_50: Optional[Decimal] = None
    sma_200: Optional[Decimal] = None

    ema_10: Optional[Decimal] = None
    ema_20: Optional[Decimal] = None

    rsi_14: Optional[Decimal] = Field(default=None, ge=0, le=100)

    macd: Optional[Decimal] = None
    macd_signal: Optional[Decimal] = None
    macd_histogram: Optional[Decimal] = None

    bollinger_upper: Optional[Decimal] = None
    bollinger_middle: Optional[Decimal] = None
    bollinger_lower: Optional[Decimal] = None

    atr_14: Optional[Decimal] = Field(default=None, ge=0)

    mfi_14: Optional[Decimal] = Field(default=None, ge=0, le=100)

    vwap: Optional[Decimal] = None

    obv: Optional[int] = None


class MarketSnapshot(BaseModel):
    ticker: str
    timestamp: datetime
    bar: OHLCVBar
    indicators: Optional[TechnicalIndicators] = None
    prev_close: Optional[Decimal] = None

    @property
    def change(self) -> Optional[Decimal]:
        if self.prev_close:
            return self.bar.close - self.prev_close
        return None

    @property
    def change_percent(self) -> Optional[Decimal]:
        if self.prev_close and self.prev_close > 0:
            return ((self.bar.close - self.prev_close) / self.prev_close) * 100
        return None


class HistoricalDataRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    start_date: date
    end_date: date
    interval: str = Field(default="1d")
    include_indicators: bool = Field(default=True)
    adjusted: bool = Field(default=True)

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        if "start_date" in info.data and v < info.data["start_date"]:
            raise ValueError("end_date must be >= start_date")
        return v


class HistoricalDataResponse(BaseModel):
    request: HistoricalDataRequest
    ohlcv: OHLCV
    indicators: list[TechnicalIndicators] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=datetime.now)
    source: str = Field(default="unknown")
