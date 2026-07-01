"""Deterministic numeric guardrails for evidence-backed decisions."""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel

from tradingagents.evidence import stable_json_hash

GuardrailStatus = Literal["pass", "warn", "blocked"]


class QuantitativeAnchor(BaseModel):
    anchor_id: str
    symbol: str
    as_of_date: str
    current_price: float | None
    evidence_id: str
    source: str = "verified_market_snapshot"
    latest_date: str | None = None


class MathGuardrailEvent(BaseModel):
    rule_id: str
    status: GuardrailStatus
    message: str
    action: str
    actual_value: float | None = None
    threshold: float | None = None
    evidence_id: str | None = None
    anchor_id: str | None = None


def build_market_price_anchor(
    symbol: str,
    as_of_date: str,
    market_snapshot_payload: dict[str, Any],
    evidence_id: str,
) -> QuantitativeAnchor:
    current_price = _coerce_positive_float(
        market_snapshot_payload.get("latest_ohlcv", {}).get("Close")
    )
    anchor_material = {
        "symbol": symbol.upper(),
        "as_of_date": as_of_date,
        "current_price": current_price,
        "evidence_id": evidence_id,
    }
    return QuantitativeAnchor(
        anchor_id=f"QA-{stable_json_hash(anchor_material)}",
        symbol=symbol.upper(),
        as_of_date=as_of_date,
        current_price=current_price,
        evidence_id=evidence_id,
        latest_date=market_snapshot_payload.get("latest_date"),
    )


class MathGuardrailEngine:
    def __init__(self, warn_multiple: float = 3.0, block_multiple: float = 5.0):
        self.warn_multiple = warn_multiple
        self.block_multiple = block_multiple

    def check_price_target(
        self,
        anchor: QuantitativeAnchor,
        price_target: float | None,
    ) -> list[MathGuardrailEvent]:
        if price_target is None:
            return []

        target = _coerce_float(price_target)
        if target is None or target <= 0:
            return [
                MathGuardrailEvent(
                    rule_id="price_target_positive",
                    status="blocked",
                    message="Price target must be a positive numeric value.",
                    action="remove_target_price",
                    actual_value=target,
                    evidence_id=anchor.evidence_id,
                    anchor_id=anchor.anchor_id,
                )
            ]

        current = anchor.current_price
        if current is None or current <= 0:
            return [
                MathGuardrailEvent(
                    rule_id="current_price_available",
                    status="warn",
                    message="Current price is unavailable; target-price multiple check skipped.",
                    action="skip_target_price_check",
                    actual_value=current,
                    evidence_id=anchor.evidence_id,
                    anchor_id=anchor.anchor_id,
                )
            ]

        multiple = max(target / current, current / target)
        if multiple >= self.block_multiple:
            return [
                MathGuardrailEvent(
                    rule_id="price_target_multiple",
                    status="blocked",
                    message="Price target is far outside the verified current-price anchor.",
                    action="remove_or_rejustify_target_price",
                    actual_value=multiple,
                    threshold=self.block_multiple,
                    evidence_id=anchor.evidence_id,
                    anchor_id=anchor.anchor_id,
                )
            ]
        if multiple >= self.warn_multiple:
            return [
                MathGuardrailEvent(
                    rule_id="price_target_multiple",
                    status="warn",
                    message="Price target is materially outside the verified current-price anchor.",
                    action="review_target_price",
                    actual_value=multiple,
                    threshold=self.warn_multiple,
                    evidence_id=anchor.evidence_id,
                    anchor_id=anchor.anchor_id,
                )
            ]
        return []


def _coerce_positive_float(value: Any) -> float | None:
    coerced = _coerce_float(value)
    if coerced is None or coerced <= 0:
        return None
    return coerced


def _coerce_float(value: Any) -> float | None:
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(coerced):
        return None
    return coerced
