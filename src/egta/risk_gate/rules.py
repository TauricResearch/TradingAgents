"""Deterministic FR-04 rules and limit calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from .canonical import hash_is_valid, recompute_evidence_hash
from .models import ReasonCode, VerdictStatus


@dataclass(frozen=True)
class Decision:
    status: VerdictStatus
    reasons: tuple[ReasonCode, ...]
    checked_rules: tuple[str, ...]
    side: str | None = None
    quantity: int | None = None
    exec_price: Decimal | None = None
    fee: Decimal | None = None
    cash_after: Decimal | None = None
    position_after: int | None = None
    nav_after: Decimal | None = None

    @property
    def executes(self) -> bool:
        return self.side is not None


def _decision(
    status: VerdictStatus, reason: ReasonCode, checked: str
) -> Decision:
    return Decision(status=status, reasons=(reason,), checked_rules=(checked,))


def _reject(reason: ReasonCode, checked: str) -> Decision:
    return _decision(VerdictStatus.REJECTED, reason, checked)


def _review(reason: ReasonCode, checked: str) -> Decision:
    return _decision(VerdictStatus.REVIEW, reason, checked)


def _blocked(reason: ReasonCode, checked: str) -> Decision:
    return _decision(VerdictStatus.BLOCKED, reason, checked)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_aware(value: Any) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _parse_price(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError):
            return None
        return parsed if parsed.is_finite() else None
    return None


def _quantize(value: Decimal, quantum: Decimal | None) -> Decimal:
    if quantum is None:
        return value
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _check_claims(claims: Any, evidence_pack: Any) -> Decision | None:
    if not claims:
        return None
    items = getattr(evidence_pack, "items", ()) or ()
    by_id = {getattr(item, "evidence_id", None): item for item in items}
    for claim in claims:
        evidence_ids = getattr(claim, "evidence_ids", ()) or ()
        if not evidence_ids:
            return _review(ReasonCode.INVALID_CITATION, "claims")
        usable = False
        missing = False
        causes: list[ReasonCode] = []
        for evidence_id in evidence_ids:
            item = by_id.get(evidence_id)
            if item is None:
                missing = True
                continue
            availability = getattr(item, "availability", None)
            if availability == "available":
                usable = True
            elif availability == "unreachable":
                causes.append(ReasonCode.VENDOR_UNAVAILABLE)
            elif availability == "stale":
                causes.append(ReasonCode.STALE_DATA)
            else:
                causes.append(ReasonCode.EVIDENCE_MISSING)
        if usable:
            continue
        if missing:
            return _review(ReasonCode.INVALID_CITATION, "claims")
        if causes:
            return _review(causes[0], "evidence_availability")
        return _review(ReasonCode.EVIDENCE_MISSING, "claims")
    return None


def decide(
    proposal: Any,
    evidence_pack: Any,
    db_portfolio: Any,
    current_portfolio: Any,
    policy: Any,
    now: datetime,
) -> Decision:
    action = getattr(proposal, "action", None)
    if action not in {"BUY", "SELL", "HOLD"}:
        return _reject(ReasonCode.INVALID_OUTPUT, "action")
    allowed = set(getattr(policy, "allowed_actions", ()) or ())
    if action not in allowed:
        return _reject(ReasonCode.INVALID_OUTPUT, "action")

    proposal_version = getattr(proposal, "portfolio_version", None)
    current_version = getattr(current_portfolio, "version", None)
    db_version = getattr(db_portfolio, "version", None)
    if not _is_int(proposal_version):
        return _reject(ReasonCode.INVALID_OUTPUT, "portfolio_version")
    if current_version != db_version or proposal_version != db_version:
        if proposal_version != db_version:
            return Decision(
                status=VerdictStatus.STALE_PORTFOLIO,
                reasons=(ReasonCode.STALE_PORTFOLIO,),
                checked_rules=("portfolio_version",),
            )
        return _reject(ReasonCode.STALE_PORTFOLIO, "portfolio_version")

    cash = getattr(db_portfolio, "cash", None)
    base_currency = getattr(db_portfolio, "base_currency", None)
    positions = tuple(getattr(db_portfolio, "positions", ()) or ())
    if not isinstance(cash, Decimal) or cash < 0:
        return _blocked(ReasonCode.INCOMPATIBLE_STATE, "portfolio")
    if not isinstance(base_currency, str) or not base_currency:
        return _blocked(ReasonCode.INCOMPATIBLE_STATE, "portfolio")
    for position in positions:
        quantity = getattr(position, "quantity", None)
        mark_price = getattr(position, "mark_price", None)
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0:
            return _blocked(ReasonCode.INCOMPATIBLE_STATE, "portfolio")
        if not isinstance(mark_price, Decimal) or mark_price <= 0:
            return _blocked(ReasonCode.INCOMPATIBLE_STATE, "portfolio")

    ticker = getattr(proposal, "ticker", None)
    quantity = getattr(proposal, "quantity", None)
    reference_price = getattr(proposal, "reference_price", None)
    currency = getattr(proposal, "currency", None)
    price_time = getattr(proposal, "price_time", None)
    expires_at = getattr(proposal, "expires_at", None)
    claims = getattr(proposal, "claims", ()) or ()
    price: Decimal | None = None

    if action in {"BUY", "SELL"}:
        if not isinstance(ticker, str) or not ticker:
            return _reject(ReasonCode.INVALID_OUTPUT, "ticker")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            return _reject(ReasonCode.INVALID_OUTPUT, "quantity")
        price = _parse_price(reference_price)
        if price is None or price <= 0:
            return _reject(ReasonCode.INVALID_OUTPUT, "reference_price")
        if not isinstance(currency, str) or not currency:
            return _reject(ReasonCode.INVALID_OUTPUT, "currency")
        if not claims:
            return _review(ReasonCode.EVIDENCE_MISSING, "claims")
        if (
            not isinstance(price_time, datetime)
            or price_time.tzinfo is None
            or price_time.utcoffset() is None
        ):
            return _reject(ReasonCode.INVALID_TIME, "price_time")

    if (
        not isinstance(expires_at, datetime)
        or expires_at.tzinfo is None
        or expires_at.utcoffset() is None
    ):
        return _reject(ReasonCode.INVALID_TIME, "expires_at")
    assert isinstance(expires_at, datetime)

    if evidence_pack is None:
        return _review(ReasonCode.EVIDENCE_MISSING, "evidence")
    pack_hash = getattr(evidence_pack, "pack_hash", None)
    if not hash_is_valid(pack_hash):
        return _reject(ReasonCode.INTEGRITY_VIOLATION, "evidence_hash")
    try:
        computed_pack_hash = recompute_evidence_hash(evidence_pack)
    except Exception:
        return _reject(ReasonCode.INTEGRITY_VIOLATION, "evidence_hash")
    if computed_pack_hash != pack_hash:
        return _reject(ReasonCode.INTEGRITY_VIOLATION, "evidence_hash")
    if getattr(proposal, "evidence_pack_hash", None) != pack_hash:
        return _reject(ReasonCode.INTEGRITY_VIOLATION, "evidence_binding")
    if getattr(proposal, "run_id", None) != getattr(evidence_pack, "run_id", None):
        return _reject(ReasonCode.INTEGRITY_VIOLATION, "evidence_run")

    if action in {"BUY", "SELL"}:
        assert isinstance(price_time, datetime)
        if price_time > now:
            return _reject(ReasonCode.FUTURE_DATA, "price_time")
        cutoff = getattr(evidence_pack, "cutoff", None)
        if (
            not isinstance(cutoff, datetime)
            or cutoff.tzinfo is None
            or cutoff.utcoffset() is None
            or cutoff < price_time
        ):
            return _review(ReasonCode.EVIDENCE_MISSING, "evidence_cutoff")
        freshness = int(policy.price_freshness_seconds)
        if (now - price_time).total_seconds() > freshness:
            return _reject(ReasonCode.STALE_DATA, "price_freshness")
    else:
        if (
            isinstance(price_time, datetime)
            and price_time.tzinfo is not None
            and price_time.utcoffset() is not None
        ):
            cutoff = getattr(evidence_pack, "cutoff", None)
            if (
                not isinstance(cutoff, datetime)
                or cutoff.tzinfo is None
                or cutoff.utcoffset() is None
                or cutoff < price_time
            ):
                return _review(ReasonCode.EVIDENCE_MISSING, "evidence_cutoff")

    if expires_at <= now:
        return _reject(ReasonCode.POLICY_REJECTED, "expiry")

    claim_issue = _check_claims(claims, evidence_pack)
    if claim_issue is not None:
        return claim_issue

    if action == "HOLD":
        return Decision(
            status=VerdictStatus.APPROVED,
            reasons=(),
            checked_rules=(
                "policy",
                "portfolio",
                "proposal",
                "evidence",
                "time",
                "hold",
            ),
        )

    policy_currency = getattr(policy, "base_currency", None)
    if currency != policy_currency or currency != base_currency:
        return _reject(ReasonCode.POLICY_REJECTED, "currency")

    assert isinstance(ticker, str)
    assert isinstance(quantity, int) and not isinstance(quantity, bool)
    assert price is not None
    position_map = {
        getattr(position, "symbol", None): position for position in positions
    }
    current = position_map.get(ticker)
    current_quantity = int(getattr(current, "quantity", 0)) if current is not None else 0
    if action == "SELL" and quantity > current_quantity:
        return _reject(ReasonCode.POLICY_REJECTED, "holdings")

    nav_before = cash + sum(
        (position.quantity * position.mark_price for position in positions),
        Decimal(0),
    )
    if nav_before <= 0:
        return _reject(ReasonCode.POLICY_REJECTED, "nav")

    slippage = Decimal(policy.slippage_bps) / Decimal(10000)
    if action == "BUY":
        exec_price = price * (Decimal(1) + slippage)
    else:
        exec_price = price * (Decimal(1) - slippage)
    if exec_price <= 0:
        return _reject(ReasonCode.POLICY_REJECTED, "exec_price")

    notional = Decimal(quantity) * exec_price
    fee = notional * Decimal(policy.fee_bps) / Decimal(10000)
    if action == "BUY":
        cash_after = cash - notional - fee
        position_after = current_quantity + quantity
    else:
        cash_after = cash + notional - fee
        position_after = current_quantity - quantity

    other_value = sum(
        (
            position.quantity * position.mark_price
            for position in positions
            if getattr(position, "symbol", None) != ticker
        ),
        Decimal(0),
    )
    nav_after = cash_after + other_value + Decimal(position_after) * exec_price
    if cash_after < 0:
        return _reject(ReasonCode.POLICY_REJECTED, "cash")
    if notional > Decimal(policy.max_order_pct) * nav_before:
        return _reject(ReasonCode.POLICY_REJECTED, "notional")
    if action == "BUY":
        if nav_after <= 0:
            return _reject(ReasonCode.POLICY_REJECTED, "nav_after")
        concentration = Decimal(position_after) * exec_price / nav_after
        if concentration > Decimal(policy.max_position_pct):
            return _reject(ReasonCode.POLICY_REJECTED, "concentration")

    quantum = getattr(policy, "quantization", None)
    return Decision(
        status=VerdictStatus.APPROVED,
        reasons=(),
        checked_rules=(
            "policy",
            "portfolio",
            "proposal",
            "evidence",
            "time",
            "currency",
            "limits",
        ),
        side=action,
        quantity=quantity,
        exec_price=exec_price,
        fee=_quantize(fee, quantum),
        cash_after=_quantize(cash_after, quantum),
        position_after=position_after,
        nav_after=nav_after,
    )
