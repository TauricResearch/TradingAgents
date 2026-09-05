"""Validated artifacts produced by research agents."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TradeDirection(str, Enum):
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"


class TradeHorizon(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class ThesisScenario(str, Enum):
    BULL = "bull"
    BASE = "base"
    BEAR = "bear"


class AgentOutputType(str, Enum):
    ANALYST_NOTE = "analyst_note"
    INVESTMENT_THESIS = "investment_thesis"
    TRADE_SIGNAL = "trade_signal"
    COCKPIT_PANEL = "cockpit_panel"


class EvidenceRef(BaseModel):
    """Reference to a deterministic data artifact or cited source."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    as_of_date: date
    confidence: float = Field(ge=0.0, le=1.0)


class AgentOutputSection(BaseModel):
    """Report/cockpit section inside a structured agent output."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    summary: str | None = Field(default=None, min_length=1)
    bullets: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class AnalystNote(BaseModel):
    """Structured analyst observation used by downstream research flows."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    analyst_role: str = Field(min_length=1)
    as_of_date: date
    summary: str = Field(min_length=1)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM


class InvestmentThesis(BaseModel):
    """Bull/base/bear thesis package for a ticker."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    as_of_date: date
    base_case: str = Field(min_length=1)
    bull_case: str = Field(min_length=1)
    bear_case: str = Field(min_length=1)
    catalysts: list[str] = Field(default_factory=list)
    disconfirming_evidence: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class TradeSignal(BaseModel):
    """Machine-consumable signal produced from a validated thesis."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    as_of_date: date
    direction: TradeDirection
    horizon: TradeHorizon
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)
    proposed_position_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    expected_return_pct: float | None = None
    stop_loss_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    invalidation_triggers: list[str] = Field(default_factory=list)


AgentPayload = AnalystNote | InvestmentThesis | TradeSignal
MetadataValue = str | int | float | bool | None


class AgentOutputEnvelope(BaseModel):
    """Stable envelope for one complete agent output.

    The envelope keeps cockpit/report metadata separate from the typed payload
    so downstream tools can render, cache, diff, and validate agent output
    without re-parsing markdown.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    as_of_date: date
    agent_id: str = Field(min_length=1)
    agent_role: str = Field(min_length=1)
    output_type: AgentOutputType
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    sections: list[AgentOutputSection] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    payload: AgentPayload | None = None
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _payload_matches_envelope(self) -> "AgentOutputEnvelope":
        if self.payload is None:
            return self

        if self.payload.symbol != self.symbol:
            raise ValueError("payload symbol must match envelope symbol")
        if self.payload.as_of_date != self.as_of_date:
            raise ValueError("payload as_of_date must match envelope as_of_date")

        expected_type = _payload_output_type(self.payload)
        if self.output_type != expected_type:
            raise ValueError("payload type must match envelope output_type")
        return self


def _payload_output_type(payload: AgentPayload) -> AgentOutputType:
    if isinstance(payload, AnalystNote):
        return AgentOutputType.ANALYST_NOTE
    if isinstance(payload, InvestmentThesis):
        return AgentOutputType.INVESTMENT_THESIS
    return AgentOutputType.TRADE_SIGNAL
