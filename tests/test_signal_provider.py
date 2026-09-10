from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from tradingagents.signals import MockSignalProvider, NormalizedSignal


def test_normalized_signal():
    signal = NormalizedSignal(
        source="finbert",
        symbol="NVDA",
        signal_type="sentiment",
        score=-0.72,
        timestamp="2026-09-10T05:00:00Z",
    )

    assert signal.source == "finbert"
    assert signal.symbol == "NVDA"
    assert signal.signal_type == "sentiment"
    assert signal.score == -0.72

def test_confidence_is_optional():
    signal = NormalizedSignal(
        source="technical",
        symbol="AAPL",
        signal_type="momentum",
        score=0.5,
        timestamp="2026-09-10T05:00:00Z",
    )

    assert signal.confidence is None

def test_provider_signal_id_is_optional():
    signal = NormalizedSignal(
        source="finbert",
        symbol="NVDA",
        signal_type="sentiment",
        score=0.4,
        timestamp="2026-09-10T05:00:00Z",
    )

    assert signal.provider_signal_id is None

def test_timestamp_is_normalized_to_utc():
    jst = timezone(timedelta(hours=9))

    signal = NormalizedSignal(
        source="example",
        symbol="NVDA",
        signal_type="sentiment",
        score=0.2,
        timestamp=datetime(2026, 9, 10, 14, 0, tzinfo=jst),
    )

    assert signal.timestamp == datetime(
        2026, 9, 10, 5, 0, tzinfo=timezone.utc
    )

def test_naive_timestamp_is_rejected():
    with pytest.raises(ValidationError):
        NormalizedSignal(
            source="example",
            symbol="NVDA",
            signal_type="sentiment",
            score=0.2,
            timestamp=datetime(2026, 9, 10, 14, 0),
        )

def test_mock_provider_filters_by_symbol():
    signals = [
        NormalizedSignal(
            source="example",
            symbol="NVDA",
            signal_type="sentiment",
            score=0.8,
            timestamp="2026-09-10T05:00:00Z",
        ),
        NormalizedSignal(
            source="example",
            symbol="AAPL",
            signal_type="sentiment",
            score=-0.3,
            timestamp="2026-09-10T05:00:00Z",
        ),
    ]

    provider = MockSignalProvider(signals)

    result = provider.get_signals("NVDA")

    assert len(result) == 1
    assert result[0].symbol == "NVDA"

