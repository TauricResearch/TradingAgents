"""Provider-neutral evidence records and the initial Yahoo trust policy."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

from tradingagents.domain import EvidenceField, SourceObservation, TrustAssessment, TrustLevel


def _business_days_between(start: date, end: date) -> int:
    if end <= start:
        return 0
    return sum(1 for offset in range(1, (end - start).days + 1) if (start.toordinal() + offset) % 7 not in {0, 6})


def _latest_price(snapshot: dict[str, Any], cutoff: str) -> tuple[Any, str | None]:
    points = [point for point in snapshot.get("price_series", []) if point.get("date", "") <= cutoff]
    if not points:
        return None, None
    latest = max(points, key=lambda point: point["date"])
    return latest.get("adjusted_close"), latest.get("date")


def assess_result_evidence(
    result: dict[str, Any],
    *,
    job_id: str | None = None,
    conversation_id: str | None = None,
    retrieved_at: str | None = None,
) -> tuple[SourceObservation, TrustAssessment]:
    snapshot = result.get("fund_snapshot") or {}
    china_snapshot = result.get("china_fund_snapshot") or snapshot.get("china_fund_snapshot")
    if isinstance(china_snapshot, dict):
        return _assess_china_fund_result(
            result,
            china_snapshot,
            job_id=job_id,
            conversation_id=conversation_id,
            retrieved_at=retrieved_at,
        )
    instrument = snapshot.get("instrument") or {}
    profile = snapshot.get("profile") or {}
    cutoff = str(result.get("trade_date") or result.get("analysis_date") or date.today().isoformat())
    retrieved_at = retrieved_at or snapshot.get("observed_at") or datetime.now(UTC).isoformat()
    source = str(snapshot.get("source") or "yahoo_finance")
    reference = str(instrument.get("canonical_symbol") or result.get("company_of_interest") or "unknown")
    normalized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str).encode()
    observation = SourceObservation(
        str(uuid.uuid4()), job_id, conversation_id, source, reference, retrieved_at,
        None, cutoff, hashlib.sha256(normalized).hexdigest(), "miss",
    )
    evidence: list[EvidenceField] = []
    reasons: list[str] = []
    warnings: list[str] = list(snapshot.get("warnings") or [])

    def add(name: str, value: Any, unit: str | None, effective_at: str | None, freshness: str, *field_warnings: str) -> None:
        evidence.append(EvidenceField(
            name, value, unit, observation.id, reference, retrieved_at, None,
            effective_at, observation.raw_hash, freshness, tuple(field_warnings),
        ))

    symbol = instrument.get("canonical_symbol") or result.get("company_of_interest")
    currency = instrument.get("currency")
    price, price_date = _latest_price(snapshot, cutoff)
    add("instrument_identity", symbol, None, cutoff, "fresh" if symbol else "missing")
    add("currency", currency, None, cutoff, "fresh" if currency else "missing")
    freshness = "missing"
    if price_date:
        lag = _business_days_between(date.fromisoformat(price_date), date.fromisoformat(cutoff))
        freshness = "fresh" if lag <= 2 else "stale"
    add("cutoff_price", price, currency, price_date, freshness)
    nav_date = profile.get("nav_as_of")
    add("nav", profile.get("nav"), currency, nav_date, "fresh" if profile.get("nav") is not None else "missing")
    add("top_holdings", snapshot.get("top_holdings") or None, "weight", snapshot.get("metadata_as_of"), "fresh" if snapshot.get("top_holdings") else "missing")

    for key, value in instrument.items():
        if key not in {"canonical_symbol", "currency"}:
            add(f"instrument.{key}", value, None, cutoff, "fresh" if value is not None else "missing")
    for key, value in profile.items():
        if key != "nav":
            effective_at = (
                value if key.endswith("_as_of") else profile.get(f"{key}_as_of")
            ) or snapshot.get("metadata_as_of")
            add(f"profile.{key}", value, currency if key in {"market_price"} else None, effective_at, "fresh" if value is not None else "missing")
    for index, metric in enumerate(snapshot.get("metrics") or []):
        add(
            f"metrics.{index}", metric, metric.get("unit") if isinstance(metric, dict) else None,
            cutoff, "fresh" if metric else "missing",
        )
    for index, holding in enumerate(snapshot.get("top_holdings") or []):
        add(f"top_holdings.{index}", holding, "weight", snapshot.get("metadata_as_of"), "fresh")
    for group in ("sectors", "asset_classes"):
        for key, value in (snapshot.get(group) or {}).items():
            add(f"{group}.{key}", value, "weight", snapshot.get("metadata_as_of"), "fresh")
    add("price_series", snapshot.get("price_series") or None, currency, price_date, freshness)
    benchmark_series = snapshot.get("benchmark_series") or [
        {"date": point.get("date"), "adjusted_close": point.get("benchmark")}
        for point in snapshot.get("price_series", [])
        if point.get("benchmark") is not None
    ]
    add("benchmark_series", benchmark_series or None, currency, price_date, "fresh" if benchmark_series else "missing")

    if not symbol:
        reasons.append("IDENTITY_MISSING")
    if not currency:
        reasons.append("CURRENCY_MISSING")
    if price is None:
        reasons.append("CUTOFF_PRICE_MISSING")
    elif freshness == "stale":
        reasons.append("CUTOFF_PRICE_STALE")
    critical_failure = bool(reasons)
    if not snapshot.get("top_holdings"):
        reasons.append("OPTIONAL_HOLDINGS_MISSING")
    benchmark_available = bool(snapshot.get("benchmark_series")) or any(
        point.get("benchmark") is not None for point in snapshot.get("price_series", [])
    )
    if not benchmark_available:
        reasons.append("BENCHMARK_EVIDENCE_MISSING")

    if critical_failure:
        level = TrustLevel.INSUFFICIENT
    elif any(code.startswith("OPTIONAL_") or code.startswith("BENCHMARK_") for code in reasons):
        level = TrustLevel.USABLE_WITH_WARNING
    else:
        level = TrustLevel.TRUSTED
    executable = level == TrustLevel.TRUSTED
    assessment = TrustAssessment(
        str(uuid.uuid4()), job_id, conversation_id, level, executable,
        tuple(reasons), tuple(dict.fromkeys(warnings)), datetime.now(UTC).isoformat(), tuple(evidence),
    )
    return observation, assessment


def _assess_china_fund_result(
    result: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    job_id: str | None,
    conversation_id: str | None,
    retrieved_at: str | None,
) -> tuple[SourceObservation, TrustAssessment]:
    identity = snapshot.get("identity") or {}
    trust = snapshot.get("trust") or {}
    evidence_payload = snapshot.get("evidence") or []
    retrieved_at = retrieved_at or snapshot.get("retrieved_at") or datetime.now(UTC).isoformat()
    normalized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str).encode()
    references = [
        str(item.get("source_reference"))
        for item in evidence_payload
        if item.get("source_reference")
    ]
    observation = SourceObservation(
        str(uuid.uuid4()),
        job_id,
        conversation_id,
        "china_public_fund",
        references[0] if references else str(identity.get("code") or "unknown"),
        retrieved_at,
        None,
        str(snapshot.get("analysis_date") or result.get("trade_date")),
        hashlib.sha256(normalized).hexdigest(),
        "normalized",
    )
    evidence = []
    for item in evidence_payload:
        value = dict(item)
        value["normalization_warnings"] = tuple(value.get("normalization_warnings") or ())
        evidence.append(EvidenceField(**value))
    assessment = TrustAssessment(
        str(uuid.uuid4()),
        job_id,
        conversation_id,
        str(trust.get("level") or TrustLevel.INSUFFICIENT),
        bool(trust.get("executable")),
        tuple(trust.get("reason_codes") or ()),
        tuple(trust.get("warnings") or ()),
        str(trust.get("assessed_at") or datetime.now(UTC).isoformat()),
        tuple(evidence),
    )
    return observation, assessment


def assess_provider_rate_limited(*, job_id: str, observed_at: str) -> TrustAssessment:
    """Persist a deterministic non-evidence trust outcome for provider outage.

    A throttle response is operational metadata, not financial evidence.  The
    empty evidence set preserves that distinction while making the job's trust
    state recoverable and explicit.
    """
    return TrustAssessment(
        str(uuid.uuid4()),
        job_id,
        None,
        TrustLevel.INSUFFICIENT,
        False,
        ("PROVIDER_RATE_LIMITED",),
        ("Yahoo Finance data was unavailable because the provider rate limited this request.",),
        observed_at,
        (),
    )


def assess_provider_timed_out(*, job_id: str, observed_at: str) -> TrustAssessment:
    """Persist a deterministic non-evidence trust outcome for provider timeout."""
    return TrustAssessment(
        str(uuid.uuid4()),
        job_id,
        None,
        TrustLevel.INSUFFICIENT,
        False,
        ("PROVIDER_TIMED_OUT",),
        ("Yahoo Finance did not respond within the configured request timeout.",),
        observed_at,
        (),
    )
