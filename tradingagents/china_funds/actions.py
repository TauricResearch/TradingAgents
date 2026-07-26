"""Deterministic off-exchange fund action eligibility."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .domain import ChinaFundSnapshot, FundAction, FundEvaluation


def _positive(value: str | None) -> bool:
    try:
        return value is not None and Decimal(value) > 0
    except (InvalidOperation, ValueError):
        return False


def _status_open(value: str) -> bool:
    lowered = value.casefold()
    return lowered in {"open", "开放申购", "开放赎回", "开放"} or "开放" in lowered


def evaluate_actions(
    snapshot: ChinaFundSnapshot,
    *,
    intended_action: str = "hold",
    amount: str | None = None,
    unit_fraction: str | None = None,
    confirmed_units: str | None = None,
    holding_days: int | None = None,
    minimum_holding_known: bool = False,
    sales_platform: str | None = None,
    conversion_supported: bool = False,
    target_snapshot: ChinaFundSnapshot | None = None,
) -> FundEvaluation:
    selected = FundAction(intended_action)
    blocked: dict[str, tuple[str, ...]] = {}
    allowed: list[FundAction] = []
    trust = snapshot.trust
    common: list[str] = []
    if trust.get("level") == "insufficient":
        common.extend(
            code
            for code in trust.get("reason_codes", [])
            if code in {"IDENTITY_UNVERIFIED", "NAV_MISSING", "NAV_STALE"}
        )

    hold_reasons = tuple(common)
    if hold_reasons:
        blocked[FundAction.HOLD] = hold_reasons
    else:
        allowed.append(FundAction.HOLD)

    subscribe_reasons = list(common)
    status = snapshot.transaction_status
    if "TRANSACTION_STATUS_STALE" in trust.get("reason_codes", []):
        subscribe_reasons.append("TRANSACTION_STATUS_STALE")
    if status is None or not _status_open(status.subscription):
        subscribe_reasons.append("SUBSCRIPTION_CLOSED" if status else "TRANSACTION_STATUS_MISSING")
    if selected == FundAction.SUBSCRIBE and not _positive(amount):
        subscribe_reasons.append("SUBSCRIPTION_AMOUNT_REQUIRED")
    if subscribe_reasons:
        blocked[FundAction.SUBSCRIBE] = tuple(dict.fromkeys(subscribe_reasons))
    else:
        allowed.append(FundAction.SUBSCRIBE)

    redeem_reasons = list(common)
    if "TRANSACTION_STATUS_STALE" in trust.get("reason_codes", []):
        redeem_reasons.append("TRANSACTION_STATUS_STALE")
    if status is None or not _status_open(status.redemption):
        redeem_reasons.append("REDEMPTION_CLOSED" if status else "TRANSACTION_STATUS_MISSING")
    if not _positive(confirmed_units):
        redeem_reasons.append("CONFIRMED_UNITS_REQUIRED")
    redeem_fees = [item for item in snapshot.fees if item.action == "redeem"]
    if not redeem_fees or holding_days is None:
        redeem_reasons.append("FEE_RULE_UNKNOWN")
    if selected == FundAction.REDEEM_PARTIAL:
        try:
            fraction = Decimal(unit_fraction or "")
            if fraction <= 0 or fraction >= 1:
                raise ValueError
        except (InvalidOperation, ValueError):
            redeem_reasons.append("REDEMPTION_FRACTION_REQUIRED")
    if redeem_reasons:
        blocked[FundAction.REDEEM_PARTIAL] = tuple(dict.fromkeys(redeem_reasons))
    else:
        allowed.append(FundAction.REDEEM_PARTIAL)

    redeem_all_reasons = list(redeem_reasons)
    if not minimum_holding_known:
        redeem_all_reasons.append("MINIMUM_HOLDING_RULE_UNKNOWN")
    if redeem_all_reasons:
        blocked[FundAction.REDEEM_ALL] = tuple(dict.fromkeys(redeem_all_reasons))
    else:
        allowed.append(FundAction.REDEEM_ALL)

    convert_reasons = list(dict.fromkeys(common + redeem_reasons))
    if not minimum_holding_known:
        convert_reasons.append("MINIMUM_HOLDING_RULE_UNKNOWN")
    if target_snapshot is None:
        convert_reasons.append("CONVERSION_TARGET_REQUIRED")
    else:
        source_parent = snapshot.identity.parent_product_id
        target_parent = target_snapshot.identity.parent_product_id
        if (
            target_snapshot.identity.code == snapshot.identity.code
            or not source_parent
            or source_parent != target_parent
        ):
            convert_reasons.append("CONVERSION_TARGET_SHARE_CLASS_MISMATCH")
        target_codes = set(target_snapshot.trust.get("reason_codes", []))
        target_reason_map = {
            "IDENTITY_UNVERIFIED": "TARGET_IDENTITY_UNVERIFIED",
            "NAV_MISSING": "TARGET_NAV_MISSING",
            "NAV_STALE": "TARGET_NAV_STALE",
            "TRANSACTION_STATUS_MISSING": "TARGET_TRANSACTION_STATUS_MISSING",
            "TRANSACTION_STATUS_STALE": "TARGET_TRANSACTION_STATUS_STALE",
        }
        convert_reasons.extend(
            mapped for code, mapped in target_reason_map.items() if code in target_codes
        )
        target_status = target_snapshot.transaction_status
        if target_status is None or not _status_open(target_status.subscription):
            convert_reasons.append(
                "TARGET_SUBSCRIPTION_CLOSED"
                if target_status
                else "TARGET_TRANSACTION_STATUS_MISSING"
            )
    if not sales_platform or not conversion_supported:
        convert_reasons.append("PLATFORM_CONVERSION_UNCONFIRMED")
    if convert_reasons:
        blocked[FundAction.CONVERT] = tuple(dict.fromkeys(convert_reasons))
    else:
        allowed.append(FundAction.CONVERT)

    executable = selected in allowed
    action_reason = {
        FundAction.SUBSCRIBE: "Subscription is open and critical data is current.",
        FundAction.HOLD: "No transaction is required; monitor the stated re-evaluation triggers.",
        FundAction.REDEEM_PARTIAL: "Partial redemption is allowed against confirmed units and known fee rules.",
        FundAction.REDEEM_ALL: "Full redemption is allowed against confirmed units and known constraints.",
        FundAction.CONVERT: "The selected platform explicitly confirms native conversion support.",
    }
    reason = (
        action_reason[selected]
        if selected in allowed
        else ", ".join(blocked.get(selected, ("ACTION_BLOCKED",)))
    )
    confidence = (
        "high"
        if executable and not snapshot.trust.get("reason_codes")
        else "medium"
        if selected in allowed
        else "low"
    )
    warnings = list(snapshot.trust.get("warnings", []))
    if selected == FundAction.CONVERT and not conversion_supported:
        warnings.append(
            "Represent conversion as redeem plus subscribe until the sales platform confirms support."
        )
    supporting = tuple(
        dict.fromkeys(
            item.name
            for item in (
                snapshot.evidence
                + (target_snapshot.evidence if target_snapshot is not None else ())
            )
            if item.freshness_status == "fresh"
        )
    )
    opposing = tuple(dict.fromkeys(blocked.get(selected, ())))
    fee_action = "subscribe" if selected == FundAction.SUBSCRIBE else "redeem"
    friction = tuple(
        {
            "kind": "fee_rule",
            "action": item.action,
            "condition": item.condition,
            "rate": item.rate,
            "source_note": item.source_note,
        }
        for item in snapshot.fees
        if item.action == fee_action or selected == FundAction.CONVERT
    )
    return FundEvaluation(
        code=snapshot.identity.code,
        action=selected,
        allowed_actions=tuple(allowed),
        blocked_actions={
            key.value if isinstance(key, FundAction) else str(key): value
            for key, value in blocked.items()
        },
        executable=executable,
        confidence=confidence,
        reason=reason,
        amount=amount if selected == FundAction.SUBSCRIBE else None,
        unit_fraction=(
            unit_fraction
            if selected == FundAction.REDEEM_PARTIAL
            else ("1.0" if selected == FundAction.REDEEM_ALL else None)
        ),
        sales_platform=sales_platform,
        conversion_supported=conversion_supported,
        target_code=target_snapshot.identity.code if target_snapshot is not None else None,
        supporting_evidence=supporting,
        opposing_evidence=opposing,
        friction=friction,
        warnings=tuple(dict.fromkeys(warnings)),
    )
