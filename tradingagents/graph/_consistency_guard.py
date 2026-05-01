"""Pure numeric extraction and fundamentals consistency checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

type Direction = Literal["expansion", "compression", "increase", "decrease"] | None
type Confidence = Literal["high", "low"]
type Unit = Literal["%", "bps", "x", "B", "M"]


@dataclass(frozen=True)
class NumericClaim:
    metric: str
    value: float
    unit: Unit
    direction: Direction
    confidence: Confidence


@dataclass(frozen=True)
class Violation:
    claim: NumericClaim
    reason: str
    evidence: str


_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<value>[+-]?(?:\$)?\d+(?:\.\d+)?)\s*(?P<unit>%|bps|x|B|M)(?=$|\s|[,.;:)])",
    re.IGNORECASE,
)
_METRIC_STOP_RE = re.compile(
    r"\b(?:and|but|while|with|as|to|from|vs|versus|over|in|at|since|have|has|a|an|the)\b",
    re.IGNORECASE,
)
_DIRECTION_TERMS: tuple[tuple[str, str], ...] = (
    ("expanded", "expansion"),
    ("expansion", "expansion"),
    ("expanding", "expansion"),
    ("compressed", "compression"),
    ("compression", "compression"),
    ("contracted", "compression"),
    ("declined", "decrease"),
    ("decreased", "decrease"),
    ("decrease", "decrease"),
    ("down", "decrease"),
    ("fell", "decrease"),
    ("reduced", "decrease"),
    ("increased", "increase"),
    ("increase", "increase"),
    ("improved", "increase"),
    ("improvement", "increase"),
    ("rose", "increase"),
    ("up", "increase"),
    ("negative", "decrease"),
)
_METRIC_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("margin", ("margin",)),
    ("leverage_debt", ("leverage", "debt")),
    ("free_cash_flow", ("free cash flow", "fcf", "cash flow")),
    ("revenue", ("revenue",)),
    ("net_income", ("net income",)),
    ("eps", ("eps", "earnings per share")),
    ("interest_expense", ("interest expense",)),
)
_TOLERANCE_BY_UNIT: dict[str, float] = {
    "%": 0.25,
    "bps": 25.0,
    "x": 0.1,
    "B": 0.25,
    "M": 25.0,
}


def extract_numeric_claims(rm_text: str) -> list[NumericClaim]:
    """Extract deterministic numeric claims from research-manager style text."""

    claims: list[NumericClaim] = []
    for match in _NUMBER_RE.finditer(rm_text):
        value = _parse_value(match.group("value"))
        unit = _normalize_unit(match.group("unit"))
        context = _claim_context(rm_text, match.start(), match.end())
        metric = _extract_metric(context)
        direction = _extract_direction(context, metric)
        claims.append(
            NumericClaim(
                metric=metric,
                value=value,
                unit=unit,
                direction=direction,
                confidence=_confidence(metric),
            )
        )
    return claims


def verify_against_fundamentals(
    claims: list[NumericClaim], fundamentals: str
) -> dict[str, list[Violation] | list[NumericClaim]]:
    """Compare extracted claims to fundamentals text without side effects."""

    fundamentals_claims = extract_numeric_claims(fundamentals)
    violations: list[Violation] = []
    flags: list[NumericClaim] = []

    for claim in claims:
        category = _category_for_metric(claim.metric)
        if claim.confidence == "low" or category is None:
            flags.append(claim)
            continue

        evidence = [
            fundamental_claim
            for fundamental_claim in fundamentals_claims
            if _category_for_metric(fundamental_claim.metric) == category
        ]
        evidence.extend(_sentence_evidence_for_category(fundamentals, category))
        if not evidence:
            flags.append(claim)
            continue

        contradiction = _find_contradiction(claim, evidence)
        if contradiction is not None:
            violations.append(contradiction)

    return {"violations": violations, "flags": flags}


def _parse_value(raw_value: str) -> float:
    value = float(raw_value.replace("$", ""))
    if value.is_integer():
        return int(value)
    return value


def _normalize_unit(raw_unit: str) -> Unit:
    unit = raw_unit.lower()
    if unit == "bps":
        return "bps"
    if unit == "x":
        return "x"
    if unit == "%":
        return "%"
    if unit == "b":
        return "B"
    return "M"


def _claim_context(text: str, start: int, end: int) -> str:
    left_boundary = max(
        text.rfind("\n", 0, start),
        text.rfind(";", 0, start),
        text.rfind(".", 0, start),
        text.rfind(",", 0, start),
    )
    for separator in (" while ", " but ", " and "):
        left_boundary = max(left_boundary, text.lower().rfind(separator, 0, start))
    right_boundary = len(text)
    for separator in ("\n", ";", ".", ","):
        idx = text.find(separator, end)
        if idx != -1:
            right_boundary = min(right_boundary, idx)
    for separator in (" while ", " but ", " and "):
        idx = text.lower().find(separator, end)
        if idx != -1:
            right_boundary = min(right_boundary, idx)
    return text[left_boundary + 1 : right_boundary].strip(" -")


def _extract_metric(context: str) -> str:
    before_number = _NUMBER_RE.split(context, maxsplit=1)[0]
    before_number = re.sub(r"^[^\w$]+", "", before_number).strip()
    for term, direction in _DIRECTION_TERMS:
        del direction
        before_number = re.sub(rf"\b{re.escape(term)}\b", "", before_number, flags=re.IGNORECASE)
    parts = [part for part in _METRIC_STOP_RE.split(before_number) if part.strip()]
    metric = parts[-1].strip(" -:()") if parts else before_number.strip(" -:()")
    metric = re.sub(r"\s+", " ", metric)
    return metric or "numeric claim"


def _extract_direction(context: str, metric: str) -> Direction:
    lowered = context.lower()
    metric_category = _category_for_metric(metric)
    for term, direction in _DIRECTION_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", lowered):
            return _normalize_direction(direction, metric_category)
    return None


def _normalize_direction(direction: str, metric_category: str | None) -> Direction:
    if direction == "increase" and metric_category == "margin":
        return "expansion"
    if direction == "decrease" and metric_category in {"margin", "leverage_debt"}:
        return "compression"
    return direction  # type: ignore[return-value]


def _confidence(metric: str) -> Confidence:
    return "high" if _category_for_metric(metric) is not None else "low"


def _category_for_metric(metric: str) -> str | None:
    normalized = metric.lower()
    for category, terms in _METRIC_CATEGORIES:
        if any(term in normalized for term in terms):
            return category
    return None


def _find_contradiction(claim: NumericClaim, evidence: list[NumericClaim]) -> Violation | None:
    opposite_directions = {
        "expansion": {"compression", "decrease"},
        "compression": {"expansion", "increase"},
        "increase": {"decrease", "compression"},
        "decrease": {"increase", "expansion"},
    }
    claim_opposites = opposite_directions.get(claim.direction or "", set())
    for item in evidence:
        if item.direction in claim_opposites:
            return Violation(
                claim=claim,
                reason=(
                    f"Claim states {claim.direction} for {claim.metric}, "
                    f"but fundamentals show {item.direction}."
                ),
                evidence=_format_evidence(item),
            )

    comparable = [
        item for item in evidence if item.unit == claim.unit and item.direction == claim.direction
    ]
    for item in comparable:
        if abs(item.value - claim.value) > _TOLERANCE_BY_UNIT.get(claim.unit, 0.0):
            return Violation(
                claim=claim,
                reason=(
                    f"Claim value {claim.value}{claim.unit} differs from fundamentals "
                    f"{item.value}{item.unit} beyond tolerance."
                ),
                evidence=_format_evidence(item),
            )
    return None


def _sentence_evidence_for_category(fundamentals: str, category: str) -> list[NumericClaim]:
    evidence: list[NumericClaim] = []
    for sentence in re.split(r"(?<=[.!?])\s+", fundamentals):
        terms = _terms_for_category(category)
        if not any(term in sentence.lower() for term in terms):
            continue
        direction = _extract_direction(sentence, terms[0])
        if direction is None:
            continue
        for match in _NUMBER_RE.finditer(sentence):
            evidence.append(
                NumericClaim(
                    metric=terms[0],
                    value=_parse_value(match.group("value")),
                    unit=_normalize_unit(match.group("unit")),
                    direction=direction,
                    confidence="high",
                )
            )
    return evidence


def _terms_for_category(category: str) -> tuple[str, ...]:
    for known_category, terms in _METRIC_CATEGORIES:
        if known_category == category:
            return terms
    return ()


def _format_evidence(claim: NumericClaim) -> str:
    direction = f" {claim.direction}" if claim.direction else ""
    return f"{claim.metric}: {claim.value}{claim.unit}{direction}"
