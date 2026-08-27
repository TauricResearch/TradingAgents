"""Deterministic research contracts, validation, and safety gating.

This module never calls an LLM and never produces an executable trading action.
It converts the Portfolio Manager's markdown into a compact, auditable record,
checks whether the supplied reports satisfy the evidence contract, and keeps a
separate research status alongside the backwards-compatible five-tier rating.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from tradingagents.agents.schemas import DataQuality, DecisionStatus
from tradingagents.agents.utils.rating import parse_rating

RESEARCH_SCHEMA_VERSION = "research-decision-v1"
RESEARCH_PROMPT_VERSION = "evidence-contract-v1"

DEFAULT_RESEARCH_SAFETY_POLICY: dict[str, Any] = {
    "enabled": True,
    "min_confidence": 0.55,
    "require_time_horizon": True,
    "require_expected_return_range": True,
    "require_invalidation_conditions": True,
    "require_key_risks": True,
    "require_sourced_evidence": True,
    "block_on_any_unavailable_data": True,
}
_BOOLEAN_POLICY_KEYS = set(DEFAULT_RESEARCH_SAFETY_POLICY) - {"min_confidence"}

_REPORT_KEYS = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}
_UNAVAILABLE_RE = re.compile(
    r"NO_DATA_AVAILABLE|DATA_UNAVAILABLE|<unavailable>|"
    r"\bdata (?:is|was|are|were) unavailable\b|\bdata unavailable\b|"
    r"status=unavailable|live-only data excluded",
    re.IGNORECASE,
)
_EVIDENCE_LEDGER_RE = re.compile(
    r"\|\s*Claim\s*\|\s*Source\s*\|\s*As Of\s*\|\s*Evidence Type\s*\|"
    r"\s*Strength\s*\|\s*Limitations\s*\|",
    re.IGNORECASE,
)
_EVIDENCE_LEDGER_ROW_RE = re.compile(
    r"^\s*\|.*\|\s*(?:Sourced Fact|Model Inference|Data Unavailable)\s*\|"
    r"\s*(?:High|Medium|Low)\s*\|.*\|\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _label_value(text: str, label: str) -> str | None:
    pattern = re.compile(
        rf"^\s*(?:\d+[.)]\s*)?\**{re.escape(label)}\**\s*:\s*(.+?)\s*$",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1).strip().strip("*").strip()
    return None


def _list_after_label(text: str, label: str) -> list[str]:
    heading = re.compile(
        rf"^\s*\**{re.escape(label)}\**\s*:\s*$",
        re.IGNORECASE,
    )
    collecting = False
    values: list[str] = []
    for line in text.splitlines():
        if heading.match(line):
            collecting = True
            continue
        if not collecting:
            continue
        stripped = line.strip()
        if not stripped:
            if values:
                break
            continue
        if stripped.startswith("- "):
            values.append(stripped[2:].strip())
            continue
        break
    return values


def _parse_percent(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.strip().replace(",", "")
    try:
        if cleaned.endswith("%"):
            return float(cleaned[:-1]) / 100.0
        parsed = float(cleaned)
        return parsed / 100.0 if parsed > 1.0 else parsed
    except ValueError:
        return None


def _parse_return_range(text: str) -> tuple[float | None, float | None]:
    value = _label_value(text, "Expected Return Range")
    if not value:
        return None, None
    match = re.match(
        r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)%)\s*(?:to|[-,])\s*"
        r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)%)\s*$",
        value,
        re.IGNORECASE,
    )
    if not match:
        return None, None
    return _parse_percent(match.group(1)), _parse_percent(match.group(2))


def _parse_enum_value(value: str | None, enum_type, default):
    if value:
        for member in enum_type:
            if member.value.lower() == value.lower():
                return member.value
    return default.value


def validate_research_safety_policy(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge and validate deterministic safety settings, failing closed on mistakes."""
    if policy is not None and not isinstance(policy, dict):
        raise ValueError("research_safety must be a mapping")
    supplied = policy or {}
    unknown = set(supplied) - set(DEFAULT_RESEARCH_SAFETY_POLICY)
    if unknown:
        raise ValueError(f"unknown research_safety option(s): {', '.join(sorted(unknown))}")
    merged = {**DEFAULT_RESEARCH_SAFETY_POLICY, **supplied}
    for key in _BOOLEAN_POLICY_KEYS:
        if not isinstance(merged[key], bool):
            raise ValueError(f"research_safety.{key} must be a boolean")
    threshold = merged["min_confidence"]
    if isinstance(threshold, bool):
        raise ValueError("research_safety.min_confidence must be a number from 0 to 1")
    try:
        threshold = float(threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "research_safety.min_confidence must be a number from 0 to 1"
        ) from exc
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("research_safety.min_confidence must be between 0 and 1")
    merged["min_confidence"] = threshold
    return merged


def _parse_evidence(text: str) -> list[dict[str, str | None]]:
    items = []
    pattern = re.compile(
        r"^- \[(Sourced Fact|Model Inference|Data Unavailable)\s*\|\s*"
        r"(High|Medium|Low)\s*\|\s*([^|]+)\s*\|\s*([^\]]+)\]\s*(.+)$",
        re.IGNORECASE,
    )
    collecting = False
    for line in text.splitlines():
        if re.match(r"^\s*\**Evidence Summary\**\s*:\s*$", line, re.IGNORECASE):
            collecting = True
            continue
        if not collecting:
            continue
        stripped = line.strip()
        if not stripped:
            if items:
                break
            continue
        match = pattern.match(stripped)
        if not match:
            break
        items.append({
            "kind": match.group(1).title(),
            "strength": match.group(2).title(),
            "source": None if match.group(3).strip().lower() == "unavailable" else match.group(3).strip(),
            "as_of": None if match.group(4).strip().lower() == "unknown" else match.group(4).strip(),
            "claim": match.group(5).strip(),
        })
    return items


def parse_portfolio_decision(text: str) -> dict[str, Any]:
    """Parse both new structured markdown and legacy free-text decisions."""
    low, high = _parse_return_range(text)
    confidence = _parse_percent(_label_value(text, "Confidence"))
    return {
        "rating": parse_rating(text),
        "model_decision_status": _parse_enum_value(
            _label_value(text, "Decision Status"),
            DecisionStatus,
            DecisionStatus.RESEARCH_COMPLETE,
        ),
        "time_horizon": _label_value(text, "Time Horizon"),
        "expected_return_low": low,
        "expected_return_high": high,
        "confidence": confidence,
        "data_quality": _parse_enum_value(
            _label_value(text, "Data Quality"),
            DataQuality,
            DataQuality.UNKNOWN,
        ),
        "invalidation_conditions": _list_after_label(text, "Invalidation Conditions"),
        "key_risks": _list_after_label(text, "Key Risks"),
        "evidence": _parse_evidence(text),
    }


def validate_evidence_contract(
    final_state: dict[str, Any],
    selected_analysts: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Validate report presence, unavailable markers, and evidence-ledger headers."""
    selected = list(selected_analysts or _REPORT_KEYS)
    checked: list[str] = []
    missing: list[str] = []
    unavailable: list[str] = []
    missing_ledgers: list[str] = []

    for analyst in selected:
        report_key = _REPORT_KEYS.get(analyst)
        if not report_key:
            continue
        checked.append(analyst)
        report = str(final_state.get(report_key) or "").strip()
        if not report:
            missing.append(analyst)
            continue
        if _UNAVAILABLE_RE.search(report):
            unavailable.append(analyst)
        if not _EVIDENCE_LEDGER_RE.search(report) or not _EVIDENCE_LEDGER_ROW_RE.search(report):
            missing_ledgers.append(analyst)

    if missing or (checked and len(unavailable) == len(checked)):
        quality = DataQuality.UNAVAILABLE.value
    elif unavailable or missing_ledgers:
        quality = DataQuality.LOW.value
    elif checked:
        quality = DataQuality.HIGH.value
    else:
        quality = DataQuality.UNKNOWN.value

    issues = []
    issues.extend(f"missing {name} report" for name in missing)
    issues.extend(f"{name} report contains unavailable data" for name in unavailable)
    issues.extend(f"{name} report lacks Evidence Ledger contract" for name in missing_ledgers)
    return {
        "quality": quality,
        "checked_analysts": checked,
        "missing_reports": missing,
        "unavailable_reports": unavailable,
        "missing_evidence_ledgers": missing_ledgers,
        "issues": issues,
    }


def evidence_ledger_excerpt(report: str, *, max_chars: int = 2_500) -> str:
    """Extract only the bounded Evidence Ledger table from an analyst report."""
    lines = report.splitlines()
    header_index = next(
        (index for index, line in enumerate(lines) if _EVIDENCE_LEDGER_RE.search(line)),
        None,
    )
    if header_index is None:
        return ""
    excerpt = []
    if header_index > 0 and "Evidence Ledger" in lines[header_index - 1]:
        excerpt.append(lines[header_index - 1].strip())
    for line in lines[header_index:]:
        if excerpt and not line.strip().startswith("|"):
            break
        excerpt.append(line.rstrip())
    return "\n".join(excerpt)[:max_chars]


def collect_evidence_context(final_state: dict[str, Any]) -> str:
    """Collect bounded analyst ledgers for the final decision prompt."""
    run_metadata = dict(final_state.get("research_run_metadata") or {})
    selected = list(run_metadata.get("selected_analysts") or _REPORT_KEYS)
    sections = []
    for analyst in selected:
        report_key = _REPORT_KEYS.get(analyst)
        if not report_key:
            continue
        excerpt = evidence_ledger_excerpt(str(final_state.get(report_key) or ""))
        if excerpt:
            sections.append(f"### {analyst.title()} Analyst Evidence\n{excerpt}")
    return "\n\n".join(sections)


_QUALITY_RANK = {
    DataQuality.UNAVAILABLE.value: 0,
    DataQuality.UNKNOWN.value: 1,
    DataQuality.LOW.value: 2,
    DataQuality.MEDIUM.value: 3,
    DataQuality.HIGH.value: 4,
}


def _worst_quality(*values: str) -> str:
    known = [value for value in values if value in _QUALITY_RANK]
    if not known:
        return DataQuality.UNKNOWN.value
    return min(known, key=_QUALITY_RANK.__getitem__)


def _bounded_text(value: Any, max_chars: int) -> str | None:
    if value is None:
        return None
    return str(value)[:max_chars]


def _bounded_text_list(values: list[Any], *, max_items: int = 10) -> list[str]:
    return [str(value)[:500] for value in values[:max_items]]


def _bounded_evidence(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bounded = []
    for item in values[:20]:
        bounded.append({
            "kind": _bounded_text(item.get("kind"), 50),
            "strength": _bounded_text(item.get("strength"), 20),
            "source": _bounded_text(item.get("source"), 300),
            "as_of": _bounded_text(item.get("as_of"), 100),
            "claim": _bounded_text(item.get("claim"), 1_000),
        })
    return bounded


def build_research_decision_record(
    final_state: dict[str, Any],
    decision_markdown: str,
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact decision record and apply the deterministic safety policy."""
    parsed = parse_portfolio_decision(decision_markdown)
    run_metadata = dict(final_state.get("research_run_metadata") or {})
    selected = list(run_metadata.get("selected_analysts") or _REPORT_KEYS)
    validation = validate_evidence_contract(final_state, selected)
    effective_policy = validate_research_safety_policy(policy)
    data_quality = _worst_quality(parsed["data_quality"], validation["quality"])

    data_reasons: list[str] = []
    no_trade_reasons: list[str] = []
    review_reasons: list[str] = []

    model_status = parsed["model_decision_status"]
    if model_status == DecisionStatus.DATA_INSUFFICIENT.value:
        data_reasons.append("Portfolio Manager marked the supplied data insufficient")
    elif model_status == DecisionStatus.NO_TRADE.value:
        no_trade_reasons.append("Portfolio Manager marked the research view No Trade")
    elif model_status == DecisionStatus.HUMAN_REVIEW_REQUIRED.value:
        review_reasons.append("Portfolio Manager requested human review")

    if validation["missing_reports"]:
        data_reasons.append("required analyst reports are missing")
    if effective_policy["block_on_any_unavailable_data"] and validation["unavailable_reports"]:
        data_reasons.append("one or more analyst reports contain unavailable data")
    if effective_policy["block_on_any_unavailable_data"] and any(
        item["kind"] == "Data Unavailable" for item in parsed["evidence"]
    ):
        data_reasons.append("the final evidence ledger contains unavailable data")
    if data_quality == DataQuality.UNAVAILABLE.value:
        data_reasons.append("overall data quality is unavailable")
    elif data_quality in {DataQuality.LOW.value, DataQuality.UNKNOWN.value}:
        review_reasons.append(f"overall data quality is {data_quality.lower()}")

    if effective_policy["require_time_horizon"] and not parsed["time_horizon"]:
        no_trade_reasons.append("forecast/holding horizon is missing")
    if effective_policy["require_expected_return_range"] and (
        parsed["expected_return_low"] is None or parsed["expected_return_high"] is None
    ):
        no_trade_reasons.append("expected return range is missing or unparseable")
    if parsed["confidence"] is None:
        no_trade_reasons.append("confidence is missing or unparseable")
    elif parsed["confidence"] < float(effective_policy["min_confidence"]):
        no_trade_reasons.append(
            f"confidence {parsed['confidence']:.0%} is below the "
            f"{float(effective_policy['min_confidence']):.0%} threshold"
        )
    if effective_policy["require_invalidation_conditions"] and not parsed[
        "invalidation_conditions"
    ]:
        no_trade_reasons.append("invalidation conditions are missing")
    if effective_policy["require_key_risks"] and not parsed["key_risks"]:
        no_trade_reasons.append("structured key risks are missing")

    sourced = [item for item in parsed["evidence"] if item["kind"] == "Sourced Fact"]
    sourced_with_time = [item for item in sourced if item.get("source") and item.get("as_of")]
    if effective_policy["require_sourced_evidence"] and not sourced_with_time:
        review_reasons.append("no sourced evidence item includes both source and as-of time")
    if validation["missing_evidence_ledgers"]:
        review_reasons.append("one or more analyst reports lack the Evidence Ledger contract")

    data_reasons = list(dict.fromkeys(data_reasons))
    no_trade_reasons = list(dict.fromkeys(no_trade_reasons))
    review_reasons = list(dict.fromkeys(review_reasons))
    if not effective_policy["enabled"]:
        gated_status = model_status
        gate_reasons: list[str] = []
    elif data_reasons:
        gated_status = DecisionStatus.DATA_INSUFFICIENT.value
        gate_reasons = data_reasons + no_trade_reasons + review_reasons
    elif no_trade_reasons:
        gated_status = DecisionStatus.NO_TRADE.value
        gate_reasons = no_trade_reasons + review_reasons
    elif review_reasons:
        gated_status = DecisionStatus.HUMAN_REVIEW_REQUIRED.value
        gate_reasons = review_reasons
    else:
        gated_status = DecisionStatus.RESEARCH_COMPLETE.value
        gate_reasons = []

    gate_passed = gated_status == DecisionStatus.RESEARCH_COMPLETE.value
    effective_action = (
        "Research Only - Rating Reference"
        if gate_passed
        else f"Research Only - {gated_status}"
    )
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "schema_version": run_metadata.get("schema_version", RESEARCH_SCHEMA_VERSION),
        "prompt_version": run_metadata.get("prompt_version", RESEARCH_PROMPT_VERSION),
        "ticker": str(final_state.get("company_of_interest") or ""),
        "analysis_date": str(final_state.get("trade_date") or ""),
        "analysis_cutoff": str(final_state.get("trade_date") or ""),
        "generated_at": generated_at,
        "model_provider": run_metadata.get("model_provider"),
        "models": dict(run_metadata.get("models") or {}),
        "selected_analysts": selected,
        "data_vendors": dict(run_metadata.get("data_vendors") or {}),
        "research_only": True,
        "rating": parsed["rating"],
        "model_decision_status": model_status,
        "decision_status": gated_status,
        "effective_action": effective_action,
        "requires_human_confirmation": not gate_passed,
        "time_horizon": _bounded_text(parsed["time_horizon"], 200),
        "expected_return_low": parsed["expected_return_low"],
        "expected_return_high": parsed["expected_return_high"],
        "confidence": parsed["confidence"],
        "data_quality": data_quality,
        "invalidation_conditions": _bounded_text_list(parsed["invalidation_conditions"]),
        "key_risks": _bounded_text_list(parsed["key_risks"]),
        "evidence": _bounded_evidence(parsed["evidence"]),
        "evidence_validation": validation,
        "safety_gate": {
            "enabled": bool(effective_policy["enabled"]),
            "passed": gate_passed,
            "reasons": gate_reasons,
            "min_confidence": float(effective_policy["min_confidence"]),
        },
    }


def render_research_safety_block(record: dict[str, Any]) -> str:
    """Render the authoritative deterministic gate beneath the PM markdown."""
    parts = [
        "---",
        "### Deterministic Research Safety Gate",
        "**Research Use Only**: Yes",
        f"**Safety-Gated Status**: {record['decision_status']}",
        f"**Effective Action**: {record['effective_action']}",
        "**Human Confirmation Required**: "
        + ("Yes" if record["requires_human_confirmation"] else "No"),
        f"**Validated Data Quality**: {record['data_quality']}",
    ]
    reasons = record.get("safety_gate", {}).get("reasons") or []
    if reasons:
        parts.append("**Gate Reasons**:")
        parts.extend(f"- {reason}" for reason in reasons)
    return "\n\n".join(parts[:2]) + "\n\n" + "\n".join(parts[2:])


def append_research_safety_block(decision_markdown: str, record: dict[str, Any]) -> str:
    """Append a gate block once, preserving the original decision verbatim."""
    if "### Deterministic Research Safety Gate" in decision_markdown:
        return decision_markdown
    return decision_markdown.rstrip() + "\n\n" + render_research_safety_block(record)


def parse_research_signal(
    decision_markdown: str,
    research_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a machine-readable, research-only signal without changing rating parsing."""
    parsed = parse_portfolio_decision(decision_markdown)
    status = None
    authoritative = False
    if research_result:
        status = research_result.get("decision_status")
        authoritative = bool(status)
    safety_status = _label_value(decision_markdown, "Safety-Gated Status")
    if safety_status:
        status = safety_status
        authoritative = True
    if not status:
        status = parsed["model_decision_status"]
    # A model-authored legacy decision can still express a restrictive status,
    # but it cannot mark itself actionable without the deterministic gate.
    if not authoritative and status == DecisionStatus.RESEARCH_COMPLETE.value:
        status = DecisionStatus.HUMAN_REVIEW_REQUIRED.value
    return {
        "rating": parsed["rating"],
        "decision_status": status,
        "research_only": True,
        "requires_human_confirmation": status != DecisionStatus.RESEARCH_COMPLETE.value,
        "time_horizon": parsed["time_horizon"],
        "expected_return_low": parsed["expected_return_low"],
        "expected_return_high": parsed["expected_return_high"],
        "confidence": parsed["confidence"],
    }
