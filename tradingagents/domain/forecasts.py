"""Canonical forecast estimates consumed by portfolio policies."""

from __future__ import annotations

import math
from enum import Enum

from pydantic import Field, field_validator

from tradingagents.domain.contracts import ContractModel
from tradingagents.domain.ids import (
    ArtifactId,
    EventId,
    ForecastId,
    InstrumentId,
    ModelId,
    ProtocolId,
    RunId,
)
from tradingagents.domain.time import AsOf


class ForecastHorizon(str, Enum):
    NEXT_OPEN_TO_OPEN = "next-open-to-open"


class ForecastEstimate(ContractModel):
    """The estimate semantics the current V2 forecaster actually provides.

    This is intentionally not named ``ForecastDistribution``: V2 does not yet
    emit variance, quantiles, or samples sufficient to support that claim.
    """

    forecast_id: ForecastId
    instrument_id: InstrumentId
    run_id: RunId
    protocol_id: ProtocolId
    model_id: ModelId
    as_of: AsOf
    horizon: ForecastHorizon
    expected_excess_return_bps: float = Field(ge=-500.0, le=500.0)
    probability_positive: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    abstain: bool
    event_ids: tuple[EventId, ...] = ()
    rationale: str
    provenance: tuple[ArtifactId, ...] = ()

    @field_validator("expected_excess_return_bps")
    @classmethod
    def validate_expected_return(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("expected excess return must be finite")
        return value
