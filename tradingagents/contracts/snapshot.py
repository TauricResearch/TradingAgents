"""MarketSnapshot: the deterministic input package handed to LLM agents.

Everything in a snapshot was computed by typed Python code (indicator
engine, macro fetchers, on-chain adapters) before any LLM sees it. Agents
read snapshots and cite their contents via DataRefs; they never compute.
The model is frozen so no node can quietly reshape the ground truth
mid-pipeline."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from tradingagents.contracts.base import SCHEMA_VERSION, ContractModel
from tradingagents.contracts.enums import AssetClass, Timeframe, TradingSession


class OHLCVBar(ContractModel):
    timeframe: Timeframe
    start: datetime = Field(description="Bar open time (UTC).")
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)

    @model_validator(mode="after")
    def _ohlc_consistent(self) -> OHLCVBar:
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError(
                f"inconsistent bar: O={self.open} H={self.high} L={self.low} C={self.close}"
            )
        return self


class SpotQuote(ContractModel):
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    last: float = Field(gt=0)
    ts: datetime

    @model_validator(mode="after")
    def _no_crossed_market(self) -> SpotQuote:
        if self.ask < self.bid:
            raise ValueError(f"crossed quote: bid={self.bid} > ask={self.ask}")
        return self


class IndicatorReading(ContractModel):
    """One deterministic indicator output, e.g. RSI(14) on H4.

    ``value`` is a mapping to accommodate multi-line indicators (MACD line /
    signal / histogram, Bollinger upper/mid/lower) without per-indicator
    models; single-value indicators use the key ``"value"``.
    """

    name: str = Field(min_length=1)
    timeframe: Timeframe
    value: dict[str, float] = Field(min_length=1)
    params: dict[str, float | int | str] = Field(default_factory=dict)


class MetricReading(ContractModel):
    """Generic named observation — macro series (DXY, US10Y, CPI YoY) and
    on-chain metrics (MVRV, SOPR, exchange reserves) share this shape."""

    name: str = Field(min_length=1)
    value: float
    unit: str | None = None
    as_of: datetime | None = None
    source: str | None = None


class NewsItem(ContractModel):
    """One news/social item with provenance, for per-claim attribution."""

    headline: str = Field(min_length=1)
    source: str = Field(min_length=1, description="Outlet or feed id, e.g. 'reuters'.")
    published_at: datetime | None = None
    url: str | None = None
    summary: str | None = None
    sentiment_hint: float | None = Field(
        default=None,
        ge=-1,
        le=1,
        description="Optional upstream sentiment score (-1..1); informational only.",
    )


class MarketSnapshot(ContractModel):
    schema_version: str = SCHEMA_VERSION
    symbol: str = Field(min_length=1)
    asset: AssetClass
    as_of: datetime
    quote: SpotQuote | None = None
    bars: list[OHLCVBar] = Field(default_factory=list)
    indicators: list[IndicatorReading] = Field(default_factory=list)
    macro: list[MetricReading] = Field(default_factory=list)
    onchain: list[MetricReading] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)
    session: TradingSession | None = None
    missing_feeds: list[str] = Field(
        default_factory=list,
        description="Feeds that failed or returned no data; agents must treat these as unknown.",
    )

    def get_indicator(self, name: str, timeframe: Timeframe) -> IndicatorReading | None:
        for reading in self.indicators:
            if reading.name == name and reading.timeframe == timeframe:
                return reading
        return None
