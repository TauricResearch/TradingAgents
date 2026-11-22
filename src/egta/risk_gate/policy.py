"""Deterministic policy validation for the FR-04 risk gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from .canonical import hash_is_valid, recompute_policy_hash
from .models import ReasonCode, VerdictStatus


@dataclass(frozen=True)
class RiskPolicy:
    version: str
    policy_hash: str
    base_currency: str
    max_position_pct: Decimal | None
    max_order_pct: Decimal | None
    price_freshness_seconds: int | None
    fee_bps: Decimal | None
    slippage_bps: Decimal | None
    allowed_actions: frozenset[str]
    long_only: bool
    paper_only: bool
    effective_from: datetime | None
    expires_at: datetime | None
    quantization: Decimal | None


@dataclass(frozen=True)
class PolicyIssue:
    status: VerdictStatus
    reason: ReasonCode


def _is_decimal(value: Any) -> bool:
    return isinstance(value, Decimal)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_aware(value: Any) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def check_policy(policy: Any, now: datetime) -> PolicyIssue | None:
    if policy is None:
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)

    stored_hash = getattr(policy, "policy_hash", None)
    if not hash_is_valid(stored_hash):
        return PolicyIssue(VerdictStatus.REJECTED, ReasonCode.INTEGRITY_VIOLATION)
    try:
        computed_hash = recompute_policy_hash(policy)
    except Exception:
        return PolicyIssue(VerdictStatus.REJECTED, ReasonCode.INTEGRITY_VIOLATION)
    if computed_hash != stored_hash:
        return PolicyIssue(VerdictStatus.REJECTED, ReasonCode.INTEGRITY_VIOLATION)

    version = getattr(policy, "version", None)
    base_currency = getattr(policy, "base_currency", None)
    max_position = getattr(policy, "max_position_pct", None)
    max_order = getattr(policy, "max_order_pct", None)
    freshness = getattr(policy, "price_freshness_seconds", None)
    fee_bps = getattr(policy, "fee_bps", None)
    slippage_bps = getattr(policy, "slippage_bps", None)
    quantization = getattr(policy, "quantization", None)

    if not isinstance(version, str) or not version:
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)
    if not isinstance(base_currency, str) or not base_currency:
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)
    if not isinstance(max_position, Decimal) or not (
        Decimal(0) < max_position <= Decimal(1)
    ):
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)
    if not isinstance(max_order, Decimal) or not (
        Decimal(0) < max_order <= Decimal(1)
    ):
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)
    if not isinstance(freshness, int) or isinstance(freshness, bool) or freshness <= 0:
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)
    if not isinstance(fee_bps, Decimal) or fee_bps < 0:
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)
    if not isinstance(slippage_bps, Decimal) or slippage_bps < 0:
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)
    if not isinstance(quantization, Decimal) or quantization <= 0:
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)

    allowed = set(getattr(policy, "allowed_actions", ()) or ())
    if not {"BUY", "SELL", "HOLD"} <= allowed:
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)
    if getattr(policy, "long_only", None) is not True:
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)
    if getattr(policy, "paper_only", None) is not True:
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)

    effective = getattr(policy, "effective_from", None)
    expires = getattr(policy, "expires_at", None)
    if (
        not isinstance(effective, datetime)
        or effective.tzinfo is None
        or effective.utcoffset() is None
    ):
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)
    if (
        not isinstance(expires, datetime)
        or expires.tzinfo is None
        or expires.utcoffset() is None
    ):
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)
    if not (effective <= now < expires):
        return PolicyIssue(VerdictStatus.BLOCKED, ReasonCode.INCOMPATIBLE_STATE)

    return None
