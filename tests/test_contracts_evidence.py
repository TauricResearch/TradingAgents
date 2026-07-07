"""Contract tests: AgentEvidence enforces the evidence discipline."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from tradingagents.contracts import (
    AgentEvidence,
    AgentTeam,
    DataRef,
    Direction,
    SourceAttribution,
    SourceType,
    Timeframe,
)


def make_source(source_id: str = "indicator_engine") -> SourceAttribution:
    return SourceAttribution(
        id=source_id,
        type=SourceType.INDICATOR,
        name="Deterministic indicator engine",
    )


def make_evidence(**overrides) -> AgentEvidence:
    fields = {
        "agent_id": "rsi_agent",
        "team": AgentTeam.TECHNICAL,
        "claim": "RSI(14) on H4 is oversold, favoring a mean-reversion bounce.",
        "direction": Direction.BULLISH,
        "confidence": 65,
        "timeframe": Timeframe.H4,
        "data_refs": [
            DataRef(
                name="RSI_14",
                value=27.4,
                timeframe=Timeframe.H4,
                source="indicator_engine",
            )
        ],
        "sources": [make_source()],
    }
    fields.update(overrides)
    return AgentEvidence(**fields)


def test_valid_evidence_round_trips_through_json():
    evidence = make_evidence()
    restored = AgentEvidence.model_validate_json(evidence.model_dump_json())
    assert restored == evidence
    assert restored.timestamp.tzinfo is not None


@pytest.mark.parametrize("confidence", [-1, 101])
def test_confidence_out_of_bounds_rejected(confidence):
    with pytest.raises(ValidationError):
        make_evidence(confidence=confidence)


def test_evidence_without_data_refs_rejected():
    with pytest.raises(ValidationError):
        make_evidence(data_refs=[])


def test_evidence_without_sources_rejected():
    with pytest.raises(ValidationError):
        make_evidence(sources=[])


def test_data_ref_citing_undeclared_source_rejected():
    with pytest.raises(ValidationError, match="undeclared sources"):
        make_evidence(
            data_refs=[DataRef(name="RSI_14", value=27.4, source="nonexistent")],
        )


def test_naive_timestamp_rejected():
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_evidence(timestamp=datetime(2026, 7, 1, 12, 0, 0))


def test_aware_timestamp_normalized_to_utc():
    import datetime as dt

    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    evidence = make_evidence(timestamp=datetime(2026, 7, 1, 17, 30, tzinfo=ist))
    assert evidence.timestamp == datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def test_evidence_is_immutable():
    evidence = make_evidence()
    with pytest.raises(ValidationError):
        evidence.confidence = 99


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        make_evidence(vibes="bullish")


def test_json_schema_exports():
    schema = AgentEvidence.model_json_schema()
    required = set(schema["required"])
    assert {"agent_id", "team", "claim", "direction", "confidence", "timeframe",
            "data_refs", "sources"} <= required
