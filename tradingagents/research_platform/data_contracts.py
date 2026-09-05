"""Normalized data contracts for the personal research platform.

These models are deliberately independent from the legacy `dataflows` module.
Existing vendor functions can be wrapped into this shape first, then replaced
or expanded without changing agent, backtest, risk, or report consumers.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timezone
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AssetClass(str, Enum):
    """Supported instrument categories for the research cockpit."""

    EQUITY = "equity"
    ETF = "etf"
    INDEX = "index"
    CRYPTO = "crypto"
    FX = "fx"
    COMMODITY = "commodity"


class InstrumentIdentity(BaseModel):
    """Canonical identity resolved before data retrieval or analysis."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    name: str | None = None
    asset_class: AssetClass = AssetClass.EQUITY
    exchange: str | None = None
    currency: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
    vendor_symbol: str | None = None


class DataProvenance(BaseModel):
    """Source metadata required for auditability and lookahead control."""

    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)
    as_of_date: date
    retrieved_at: datetime = Field(default_factory=_utc_now)
    source: str | None = None
    source_url: str | None = None
    vendor_symbol: str | None = None


class PriceBar(BaseModel):
    """One normalized OHLCV bar."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    date: date
    open: float = Field(ge=0)
    high: float = Field(ge=0)
    low: float = Field(ge=0)
    close: float = Field(ge=0)
    adjusted_close: float | None = Field(default=None, ge=0)
    adjustment_factor: float | None = Field(default=None, gt=0)
    adjustment_method: str | None = None
    volume: int | None = Field(default=None, ge=0)
    currency: str | None = None
    provenance: DataProvenance

    @model_validator(mode="after")
    def _ohlc_is_consistent(self):
        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        if self.open > self.high or self.open < self.low:
            raise ValueError("open must be within the high/low range")
        if self.close > self.high or self.close < self.low:
            raise ValueError("close must be within the high/low range")
        return self


class FundamentalSnapshot(BaseModel):
    """Point-in-time normalized fundamentals for one instrument."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    period_end: date
    fiscal_period: str | None = None
    currency: str | None = None
    metrics: dict[str, float | int | str | None] = Field(default_factory=dict)
    provenance: DataProvenance


class NewsItem(BaseModel):
    """Normalized news item with explicit publication and availability dates."""

    model_config = ConfigDict(frozen=True)

    symbol: str | None = None
    title: str = Field(min_length=1)
    published_at: datetime
    as_of_date: date
    provider: str = Field(min_length=1)
    url: str | None = None
    summary: str | None = None
    sentiment_hint: str | None = None
    source_id: str | None = None


class DataProvider(Protocol):
    """Provider interface consumed by agents, reports, backtests, and risk."""

    name: str

    def get_price_bars(
        self,
        identity: InstrumentIdentity,
        start: date,
        end: date,
        *,
        as_of_date: date | None = None,
    ) -> Sequence[PriceBar]:
        """Return daily bars available as of `as_of_date`."""

    def get_fundamentals(
        self,
        identity: InstrumentIdentity,
        *,
        as_of_date: date | None = None,
    ) -> Sequence[FundamentalSnapshot]:
        """Return point-in-time fundamentals available as of `as_of_date`."""

    def get_news(
        self,
        identity: InstrumentIdentity,
        start: date,
        end: date,
        *,
        as_of_date: date | None = None,
    ) -> Sequence[NewsItem]:
        """Return news available as of `as_of_date`."""
