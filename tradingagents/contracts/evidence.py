"""AgentEvidence: the only accepted shape for an LLM agent's analytical output.

Constraint 2 (deterministic math) and Constraint 3 (structured evidence)
meet here: every numeric value an agent cites must be a ``DataRef`` pointing
at a declared ``SourceAttribution`` — numbers enter evidence by reference to
deterministic upstream data, never as free-floating prose."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from tradingagents.contracts.base import SCHEMA_VERSION, ContractModel, utc_now
from tradingagents.contracts.enums import AgentTeam, Direction, SourceType, Timeframe


class SourceAttribution(ContractModel):
    """Where a piece of supporting data came from."""

    id: str = Field(min_length=1, description="Stable key referenced by DataRef.source.")
    type: SourceType
    name: str = Field(min_length=1, description="Human-readable source, e.g. 'FRED DGS10'.")
    url: str | None = None
    retrieved_at: datetime | None = None


class DataRef(ContractModel):
    """A single pre-computed value the agent's claim rests on."""

    name: str = Field(min_length=1, description="Metric identifier, e.g. 'RSI_14' or 'DXY'.")
    value: float | int | bool | str | None = Field(
        description="The validated, deterministically computed value being cited."
    )
    timeframe: Timeframe | None = None
    source: str = Field(min_length=1, description="Must match a SourceAttribution.id.")
    as_of: datetime | None = None


class AgentEvidence(ContractModel):
    """One agent's claim with its full supporting trail.

    Validation enforces the evidence discipline: at least one data reference,
    at least one attributed source, and every reference must resolve to a
    declared source. An agent that "just has a feeling" cannot produce a
    valid instance.
    """

    schema_version: str = SCHEMA_VERSION
    agent_id: str = Field(min_length=1)
    team: AgentTeam
    claim: str = Field(min_length=1)
    direction: Direction
    confidence: int = Field(ge=0, le=100)
    timeframe: Timeframe
    data_refs: list[DataRef] = Field(min_length=1)
    sources: list[SourceAttribution] = Field(min_length=1)
    timestamp: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _refs_resolve_to_sources(self) -> AgentEvidence:
        source_ids = {s.id for s in self.sources}
        dangling = sorted({r.source for r in self.data_refs} - source_ids)
        if dangling:
            raise ValueError(
                f"data_refs cite undeclared sources {dangling}; declared: {sorted(source_ids)}"
            )
        return self
