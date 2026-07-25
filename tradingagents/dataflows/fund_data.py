"""Best-effort yfinance adapter for normalized fund snapshots."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

from tradingagents.dataflows.yahoo import yahoo_rate_limit_error
from tradingagents.instruments import InstrumentDescriptor

from .fund_metrics import FundMetric, calculate_metrics, premium_discount

logger = logging.getLogger(__name__)


@dataclass
class FundProfile:
    category: str | None = None
    legal_type: str | None = None
    family: str | None = None
    inception_date: str | None = None
    total_assets: float | None = None
    expense_ratio: float | None = None
    yield_value: float | None = None
    nav: float | None = None
    nav_as_of: str | None = None
    market_price: float | None = None
    market_price_as_of: str | None = None


@dataclass
class FundHolding:
    symbol: str | None
    name: str | None
    weight: float | None


@dataclass
class FundSnapshot:
    instrument: InstrumentDescriptor
    observed_at: str
    metadata_as_of: str | None
    profile: FundProfile
    top_holdings: list[FundHolding] = field(default_factory=list)
    sectors: dict[str, float] = field(default_factory=dict)
    asset_classes: dict[str, float] = field(default_factory=dict)
    price_series: list[dict[str, Any]] = field(default_factory=list)
    benchmark_series: list[dict[str, Any]] = field(default_factory=list)
    metrics: list[FundMetric] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source: str = "yfinance"

    def to_dict(self) -> dict:
        return asdict(self)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if pd.notna(result) else None
    except (TypeError, ValueError):
        return None


def _date_value(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=UTC).date().isoformat()
        return pd.Timestamp(value).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _weight(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return number / 100 if number > 1 else number


def _series_from_history(history: pd.DataFrame) -> pd.Series:
    for column in ("Adj Close", "Close"):
        if column in history:
            return history[column]
    return pd.Series(dtype="float64")


def fetch_fund_snapshot(
    instrument: InstrumentDescriptor,
    analysis_date: str,
    benchmark_symbol: str = "SPY",
    *,
    ticker_factory=yf.Ticker,
) -> FundSnapshot:
    observed = datetime.now(UTC).isoformat()
    warnings: list[str] = []
    ticker = ticker_factory(instrument.canonical_symbol)
    info: dict[str, Any] = {}
    try:
        info = ticker.info or {}
    except Exception as exc:
        if limited := yahoo_rate_limit_error(exc):
            raise limited from exc
        warnings.append("Fund profile is unavailable from Yahoo Finance.")

    profile = FundProfile(
        category=info.get("category"),
        legal_type=info.get("legalType"),
        family=info.get("fundFamily"),
        inception_date=_date_value(info.get("fundInceptionDate")),
        total_assets=_number(info.get("totalAssets")),
        expense_ratio=_number(info.get("annualReportExpenseRatio") or info.get("netExpenseRatio")),
        yield_value=_number(info.get("yield")),
        nav=_number(info.get("navPrice")),
        nav_as_of=_date_value(info.get("navPriceDate")),
        market_price=_number(info.get("regularMarketPrice")),
        market_price_as_of=_date_value(info.get("regularMarketTime")),
    )

    holdings: list[FundHolding] = []
    sectors: dict[str, float] = {}
    assets: dict[str, float] = {}
    try:
        funds = ticker.funds_data
        frame = funds.top_holdings
        if isinstance(frame, pd.DataFrame):
            for index, row in frame.iterrows():
                holdings.append(FundHolding(str(index), row.get("Name"), _weight(row.get("Holding Percent"))))
        sectors = {str(k): v for k, raw in (funds.sector_weightings or {}).items() if (v := _weight(raw)) is not None}
        assets = {str(k): v for k, raw in (funds.asset_classes or {}).items() if (v := _weight(raw)) is not None}
    except Exception as exc:
        if limited := yahoo_rate_limit_error(exc):
            raise limited from exc
        warnings.append("Holdings and allocation data are unavailable from Yahoo Finance.")
    if not holdings:
        warnings.append("Top holdings are unavailable for this fund.")

    cutoff = date.fromisoformat(analysis_date)
    start = cutoff - timedelta(days=1100)
    end = cutoff + timedelta(days=1)
    prices = pd.Series(dtype="float64")
    benchmark = pd.Series(dtype="float64")
    try:
        prices = _series_from_history(ticker.history(start=start.isoformat(), end=end.isoformat(), auto_adjust=False))
    except Exception as exc:
        if limited := yahoo_rate_limit_error(exc):
            raise limited from exc
        warnings.append("Fund price history is unavailable.")
    try:
        benchmark_ticker = ticker_factory(benchmark_symbol)
        benchmark = _series_from_history(benchmark_ticker.history(start=start.isoformat(), end=end.isoformat(), auto_adjust=False))
    except Exception as exc:
        if limited := yahoo_rate_limit_error(exc):
            raise limited from exc
        warnings.append(f"Benchmark history for {benchmark_symbol} is unavailable.")

    metrics = calculate_metrics(prices, analysis_date, benchmark if not benchmark.empty else None)
    metrics.append(
        premium_discount(
            profile.market_price,
            profile.nav,
            date.fromisoformat(profile.market_price_as_of) if profile.market_price_as_of else None,
            date.fromisoformat(profile.nav_as_of) if profile.nav_as_of else None,
        )
    )
    if cutoff < datetime.now(UTC).date():
        warnings.append("Profile and holdings are latest available metadata, not historical point-in-time data.")

    def records(series: pd.Series) -> list[dict[str, Any]]:
        clean = series[series.index <= pd.Timestamp(end.isoformat(), tz=getattr(series.index, "tz", None))] if not series.empty else series
        return [{"date": pd.Timestamp(idx).date().isoformat(), "adjusted_close": float(value)} for idx, value in clean.items() if pd.notna(value) and pd.Timestamp(idx).date() <= cutoff]

    return FundSnapshot(
        instrument=instrument,
        observed_at=observed,
        metadata_as_of=None,
        profile=profile,
        top_holdings=holdings,
        sectors=sectors,
        asset_classes=assets,
        price_series=records(prices),
        benchmark_series=records(benchmark),
        metrics=metrics,
        warnings=warnings,
    )
