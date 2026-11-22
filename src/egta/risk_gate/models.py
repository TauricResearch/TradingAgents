"""Internal models for the deterministic FR-04 risk gate.

The reason-code values mirror the shared contracts v1 vocabulary accepted by B and
used by E's ``RunEvent``. The shared contract module is not part of the FR-04
implementation baseline, so this local enum is the adapter; it is not a second
public contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class VerdictStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVIEW = "REVIEW"
    BLOCKED = "BLOCKED"
    STALE_PORTFOLIO = "STALE_PORTFOLIO"


class ReasonCode(StrEnum):
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    FUTURE_DATA = "FUTURE_DATA"
    BUDGET_DENIED = "BUDGET_DENIED"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    POLICY_REJECTED = "POLICY_REJECTED"
    STALE_PORTFOLIO = "STALE_PORTFOLIO"
    AUDIT_UNAVAILABLE = "AUDIT_UNAVAILABLE"
    INCOMPATIBLE_STATE = "INCOMPATIBLE_STATE"
    INVALID_TIME = "INVALID_TIME"
    STALE_DATA = "STALE_DATA"
    VENDOR_UNAVAILABLE = "VENDOR_UNAVAILABLE"
    INVALID_CITATION = "INVALID_CITATION"
    INTEGRITY_VIOLATION = "INTEGRITY_VIOLATION"


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: int
    mark_price: Decimal


@dataclass(frozen=True)
class PortfolioSnapshot:
    portfolio_id: str
    version: int
    base_currency: str
    cash: Decimal
    positions: tuple[Position, ...]
    as_of: datetime


@dataclass(frozen=True)
class RiskVerdict:
    proposal_hash: str
    status: VerdictStatus
    reasons: tuple[ReasonCode, ...]
    checked_rules: tuple[str, ...]
    portfolio_version: int
    expires_at: datetime | None
    verdict_id: str
