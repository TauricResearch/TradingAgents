"""Canonical portfolio target contracts."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator, model_validator

from tradingagents.domain.contracts import ContractModel
from tradingagents.domain.ids import (
    ArtifactId,
    ForecastId,
    InstrumentId,
    PortfolioId,
    ProtocolId,
    RunId,
    StrategyId,
    TargetPortfolioId,
)
from tradingagents.domain.instruments import ListingRef
from tradingagents.domain.time import AsOf

_FLOAT_TOLERANCE = 1e-9


class PortfolioMode(str, Enum):
    LONG_ONLY = "long-only"


class PortfolioConstraints(ContractModel):
    mode: PortfolioMode
    gross_limit: float = Field(gt=0.0)
    max_weight: float = Field(gt=0.0)
    max_sector_weight: float = Field(gt=0.0)
    turnover_hurdle_bps: float = Field(ge=0.0)
    minimum_trade_weight: float = Field(ge=0.0)

    @field_validator(
        "gross_limit",
        "max_weight",
        "max_sector_weight",
        "turnover_hurdle_bps",
        "minimum_trade_weight",
    )
    @classmethod
    def validate_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("portfolio constraints must be finite")
        return value

    @model_validator(mode="after")
    def validate_caps(self) -> PortfolioConstraints:
        if self.max_weight > self.gross_limit:
            raise ValueError("max_weight cannot exceed gross_limit")
        if self.max_sector_weight > self.gross_limit:
            raise ValueError("max_sector_weight cannot exceed gross_limit")
        return self


class TargetAllocation(ContractModel):
    instrument_id: InstrumentId
    target_weight: float

    @field_validator("target_weight")
    @classmethod
    def validate_weight(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("target weight must be finite")
        return value


class AllocationDiagnostics(ContractModel):
    turnover: float = Field(ge=0.0)
    cash_weight: float
    active_forecasts: tuple[InstrumentId, ...] = ()
    abstentions: tuple[InstrumentId, ...] = ()
    binding_constraints: tuple[str, ...] = ()

    @field_validator("turnover", "cash_weight")
    @classmethod
    def validate_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("allocation diagnostics must be finite")
        return value


class TargetContext(ContractModel):
    target_portfolio_id: TargetPortfolioId
    portfolio_id: PortfolioId
    run_id: RunId
    strategy_id: StrategyId
    protocol_id: ProtocolId
    as_of: AsOf
    effective_at: AwareDatetime
    created_at: AwareDatetime
    producer: str
    provenance: tuple[ArtifactId, ...] = ()

    @field_validator("effective_at", "created_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @field_validator("producer")
    @classmethod
    def validate_producer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("producer must not be empty")
        return value

    @model_validator(mode="after")
    def validate_temporal_order(self) -> TargetContext:
        if self.created_at < self.as_of.decision_cutoff:
            raise ValueError("target creation cannot precede the decision cutoff")
        if self.effective_at < self.created_at:
            raise ValueError("target effective time cannot precede its creation")
        if self.as_of.entry_session is None:
            raise ValueError("portfolio targets require an explicit entry session")
        effective_session = self.effective_at.astimezone(
            ZoneInfo(self.as_of.timezone_name)
        ).date()
        if self.as_of.entry_session != effective_session:
            raise ValueError("target effective time does not match its entry session")
        return self


class TargetPortfolio(ContractModel):
    target_portfolio_id: TargetPortfolioId
    portfolio_id: PortfolioId
    run_id: RunId
    strategy_id: StrategyId
    protocol_id: ProtocolId
    as_of: AsOf
    effective_at: AwareDatetime
    created_at: AwareDatetime
    producer: str
    listings: tuple[ListingRef, ...] = Field(min_length=1)
    allocations: tuple[TargetAllocation, ...] = Field(min_length=1)
    cash_weight: float
    constraints: PortfolioConstraints
    diagnostics: AllocationDiagnostics
    forecast_ids: tuple[ForecastId, ...] = ()
    provenance: tuple[ArtifactId, ...] = ()

    @field_validator("effective_at", "created_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @field_validator("cash_weight")
    @classmethod
    def validate_cash(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("cash weight must be finite")
        return value

    @field_validator("producer")
    @classmethod
    def validate_producer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("producer must not be empty")
        return value

    @model_validator(mode="after")
    def validate_target(self) -> TargetPortfolio:
        listing_ids = [listing.instrument_id for listing in self.listings]
        if len(listing_ids) != len(set(listing_ids)):
            raise ValueError("target portfolio contains duplicate listing instruments")
        allocation_ids = [allocation.instrument_id for allocation in self.allocations]
        if len(allocation_ids) != len(set(allocation_ids)):
            raise ValueError("target portfolio contains duplicate allocations")
        if set(allocation_ids) != set(listing_ids):
            raise ValueError("target allocations must exactly match the listing universe")

        known_ids = set(listing_ids)
        if not set(self.diagnostics.active_forecasts).issubset(known_ids):
            raise ValueError("active forecasts must belong to the target universe")
        if not set(self.diagnostics.abstentions).issubset(known_ids):
            raise ValueError("abstentions must belong to the target universe")
        if set(self.diagnostics.active_forecasts) & set(self.diagnostics.abstentions):
            raise ValueError("an instrument cannot be both active and abstained")
        if len(self.forecast_ids) != len(set(self.forecast_ids)):
            raise ValueError("target portfolio contains duplicate forecast IDs")
        if self.created_at < self.as_of.decision_cutoff:
            raise ValueError("target creation cannot precede the decision cutoff")
        if self.effective_at < self.created_at:
            raise ValueError("target effective time cannot precede its creation")
        if self.as_of.entry_session is None:
            raise ValueError("portfolio targets require an explicit entry session")
        effective_session = self.effective_at.astimezone(
            ZoneInfo(self.as_of.timezone_name)
        ).date()
        if self.as_of.entry_session != effective_session:
            raise ValueError("target effective time does not match its entry session")
        for listing in self.listings:
            if listing.valid_from is not None and listing.valid_from > self.effective_at:
                raise ValueError("target contains a listing not yet valid when effective")
            if listing.valid_to is not None and listing.valid_to <= self.effective_at:
                raise ValueError("target contains a listing expired when effective")

        weights = [allocation.target_weight for allocation in self.allocations]
        if abs(sum(weights) + self.cash_weight - 1.0) > _FLOAT_TOLERANCE:
            raise ValueError("target asset and cash weights must sum to one")
        if sum(abs(weight) for weight in weights) > self.constraints.gross_limit + _FLOAT_TOLERANCE:
            raise ValueError("target gross exposure exceeds gross_limit")
        if any(
            abs(weight) > self.constraints.max_weight + _FLOAT_TOLERANCE
            for weight in weights
        ):
            raise ValueError("target position exceeds max_weight")
        if abs(self.diagnostics.cash_weight - self.cash_weight) > _FLOAT_TOLERANCE:
            raise ValueError("diagnostic cash weight does not match target cash weight")
        if any(weight < -_FLOAT_TOLERANCE for weight in weights):
            raise ValueError("long-only target cannot contain negative weights")
        if self.cash_weight < -_FLOAT_TOLERANCE:
            raise ValueError("long-only target cannot contain negative cash")
        return self

    @property
    def gross_exposure(self) -> float:
        return sum(abs(allocation.target_weight) for allocation in self.allocations)

    @property
    def net_exposure(self) -> float:
        return sum(allocation.target_weight for allocation in self.allocations)
