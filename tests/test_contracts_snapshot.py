"""Contract tests: MarketSnapshot and its deterministic building blocks."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from tradingagents.contracts import (
    AssetClass,
    IndicatorReading,
    MarketSnapshot,
    MetricReading,
    OHLCVBar,
    SpotQuote,
    Timeframe,
    TradingSession,
)

TS = datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc)


def make_bar(**overrides) -> OHLCVBar:
    fields = {
        "timeframe": Timeframe.H1,
        "start": TS,
        "open": 2400.0,
        "high": 2410.0,
        "low": 2395.0,
        "close": 2405.0,
        "volume": 12345.0,
    }
    fields.update(overrides)
    return OHLCVBar(**fields)


def make_snapshot(**overrides) -> MarketSnapshot:
    fields = {
        "symbol": "XAUUSD",
        "asset": AssetClass.GOLD,
        "as_of": TS,
        "quote": SpotQuote(bid=2404.8, ask=2405.2, last=2405.0, ts=TS),
        "bars": [make_bar()],
        "indicators": [
            IndicatorReading(
                name="RSI",
                timeframe=Timeframe.H4,
                value={"value": 27.4},
                params={"period": 14},
            ),
            IndicatorReading(
                name="MACD",
                timeframe=Timeframe.H4,
                value={"macd": -1.2, "signal": -0.8, "histogram": -0.4},
            ),
        ],
        "macro": [MetricReading(name="DXY", value=104.2, source="fred")],
        "session": TradingSession.LONDON,
    }
    fields.update(overrides)
    return MarketSnapshot(**fields)


def test_snapshot_round_trips_through_json():
    snapshot = make_snapshot()
    restored = MarketSnapshot.model_validate_json(snapshot.model_dump_json())
    assert restored == snapshot


def test_snapshot_is_immutable():
    snapshot = make_snapshot()
    with pytest.raises(ValidationError):
        snapshot.symbol = "TAMPERED"


def test_get_indicator_matches_name_and_timeframe():
    snapshot = make_snapshot()
    rsi = snapshot.get_indicator("RSI", Timeframe.H4)
    assert rsi is not None and rsi.value["value"] == 27.4
    assert snapshot.get_indicator("RSI", Timeframe.D1) is None
    assert snapshot.get_indicator("ADX", Timeframe.H4) is None


def test_bar_with_high_below_close_rejected():
    with pytest.raises(ValidationError, match="inconsistent bar"):
        make_bar(high=2401.0)


def test_bar_with_low_above_open_rejected():
    with pytest.raises(ValidationError, match="inconsistent bar"):
        make_bar(low=2401.0)


def test_crossed_quote_rejected():
    with pytest.raises(ValidationError, match="crossed quote"):
        SpotQuote(bid=2406.0, ask=2405.0, last=2405.5, ts=TS)


def test_naive_bar_start_rejected():
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_bar(start=datetime(2026, 7, 6, 14, 0))


def test_multiline_indicator_requires_at_least_one_value():
    with pytest.raises(ValidationError):
        IndicatorReading(name="MACD", timeframe=Timeframe.H4, value={})


def test_missing_feeds_recorded():
    snapshot = make_snapshot(missing_feeds=["etf_flows"], macro=[])
    assert snapshot.missing_feeds == ["etf_flows"]
