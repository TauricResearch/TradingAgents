from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from tradingagents.agents.source_registry import (
    build_source_registry,
    enrich_source_registry_with_claims,
    normalize_source_objects,
)


REPORT_CLAIM_SPECS = (
    ("market_report", "market", "market"),
    ("news_report", "news", "news"),
    ("sentiment_report", "sentiment", "sentiment"),
    ("fundamentals_report", "fundamentals", "fundamentals"),
    ("macro_report", "macro", "macro"),
)

RAW_TOOL_CLAIM_SPEC = ("raw_tool_outputs", "raw_tool_output", "raw_tool_output")

_CLAIM_SIGNAL_RE = re.compile(
    r"\b("
    r"buy|overweight|hold|underweight|sell|"
    r"uptrend|breakout|momentum|volatility|"
    r"revenue growth|cash flow|earnings|margin|"
    r"risk|macro|inflation|rates|"
    r"positive|negative|strong|weak|"
    r"beat|miss|upgrade|downgrade|liquidity|"
    r"bullish|bearish|constructive|cautious"
    r")\b",
    re.IGNORECASE,
)

_SHORT_SENTENCE_RE = re.compile(r"^[\W_]*$")
_INLINE_SOURCE_ID_RE = re.compile(r"\[(SRC-[A-Z]+-\d+|RAW-TOOL-\d+)\]")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{2,}")
_TOPIC_HINTS = (
    ("technical_trend", ("uptrend", "breakout", "higher high", "above resistance", "downtrend", "breakdown", "lower low", "below support", "bullish trend", "bearish trend")),
    ("momentum", ("momentum", "strength", "acceleration", "outperform", "gaining", "weak momentum", "deceleration", "overbought", "underperform")),
    ("volatility", ("volatility", "atr", "tight range", "wide range", "calm", "elevated volatility", "drawdown")),
    ("news_sentiment", ("upgrade", "downgrade", "beat", "miss", "positive", "negative", "strong", "warning", "approval", "partnership", "probe", "lawsuit", "headwind")),
    ("fundamentals", ("revenue growth", "cash flow", "earnings", "margin", "profit", "debt", "loss", "cash burn", "healthy balance sheet", "weak fundamentals", "impairment")),
    ("risk_posture", ("risk", "balanced", "hedge", "risk-controlled", "diversified", "disciplined", "uncertain", "conservative", "downside", "fragile", "risk-off")),
    ("macro_regime", ("macro", "inflation", "rates", "liquidity", "recession", "soft landing", "tightening", "risk-on", "favorable macro", "credit stress")),
)


@dataclass(frozen=True)
class Claim:
    claim_id: str
    claim_type: str
    state_key: str
    text: str
    source_ids: list[str]
    confidence: float
    direction: str
    rationale: str
    evidence_type: str
    counterevidence_claim_ids: list[str]
    counterevidence_source_ids: list[str]
    claim_hash: str
    topic: str


def _direction_from_text(text: str) -> str:
    lower = text.lower()
    if any(term in lower for term in ("buy", "overweight", "uptrend", "positive", "strong", "bullish", "beat", "upgrade")):
        return "bullish"
    if any(term in lower for term in ("sell", "underweight", "downtrend", "negative", "weak", "bearish", "miss", "downgrade")):
        return "bearish"
    return "neutral"


def _sentences(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part and part.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _stable_claim_id(state_key: str, text: str) -> str:
    digest = hashlib.sha256(f"{state_key}|{_normalize(text)}".encode("utf-8")).hexdigest()
    return f"CLAIM-{digest[:12].upper()}"


def _stable_claim_id_with_sources(state_key: str, text: str, source_ids: list[str]) -> str:
    digest = hashlib.sha256(
        f"{state_key}|{_normalize(text)}|{'|'.join(sorted(source_ids))}".encode("utf-8")
    ).hexdigest()
    return f"CLAIM-{digest[:12].upper()}"


def _is_fact_sentence(sentence: str) -> bool:
    if not sentence.strip() or _SHORT_SENTENCE_RE.match(sentence):
        return False
    if len(sentence.split()) < 4:
        return bool(_CLAIM_SIGNAL_RE.search(sentence))
    return True


def _source_ids_for_state_key(source_registry: dict[str, Any], state_key: str) -> list[str]:
    source_index = source_registry.get("source_index") if isinstance(source_registry, dict) else {}
    if not isinstance(source_index, dict):
        return []
    return [
        source_id
        for source_id, source in source_index.items()
        if isinstance(source, dict) and source.get("state_key") == state_key
    ]


def _topic_from_text(text: str, claim_type: str) -> str:
    lower = text.lower()
    for topic, hints in _TOPIC_HINTS:
        if any(hint in lower for hint in hints):
            return topic
    return claim_type


def _sentence_tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text)}


def _find_inline_source_ids(text: str, source_registry: dict[str, Any]) -> list[str]:
    source_index = source_registry.get("source_index") if isinstance(source_registry, dict) else {}
    if not isinstance(source_index, dict):
        return []
    matched: list[str] = []
    seen: set[str] = set()
    for source_id in _INLINE_SOURCE_ID_RE.findall(text):
        if source_id in source_index and source_id not in seen:
            seen.add(source_id)
            matched.append(source_id)
    return matched


def _find_explicit_source_ids(text: str, state_key: str, source_registry: dict[str, Any]) -> list[str]:
    source_index = source_registry.get("source_index") if isinstance(source_registry, dict) else {}
    if not isinstance(source_index, dict):
        return []
    sentence_tokens = _sentence_tokens(text)
    matched: list[str] = []
    seen: set[str] = set()
    for source_id, source in source_index.items():
        if not isinstance(source, dict):
            continue
        source_tokens = _sentence_tokens(
            " ".join(
                str(value)
                for value in (
                    source.get("label", ""),
                    source.get("tool_name", ""),
                    source.get("source_type", ""),
                )
            )
        )
        if not source_tokens.intersection(sentence_tokens):
            continue
        if source.get("state_key") == state_key or source.get("source_type") == "raw_tool_output":
            if source_id not in seen:
                seen.add(source_id)
                matched.append(source_id)
    return matched


def _resolve_evidence(text: str, state_key: str, source_registry: dict[str, Any]) -> tuple[list[str], str]:
    inline_source_ids = _find_inline_source_ids(text, source_registry)
    if inline_source_ids:
        return inline_source_ids, "inline_citation"
    explicit_source_ids = _find_explicit_source_ids(text, state_key, source_registry)
    if explicit_source_ids:
        return explicit_source_ids, "explicit_source_reference"
    report_source_ids = _source_ids_for_state_key(source_registry, state_key)
    if report_source_ids:
        return report_source_ids, "report_source_fallback"
    return [], "unlinked_text"


def _claim_confidence(text: str, source_ids: list[str], evidence_type: str) -> float:
    signal_found = bool(_CLAIM_SIGNAL_RE.search(text))
    base = 0.42
    if evidence_type == "inline_citation":
        base = 0.91
    elif evidence_type == "explicit_source_reference":
        base = 0.81
    elif evidence_type == "report_source_fallback":
        base = 0.67
    if signal_found:
        base += 0.03
    if len(source_ids) > 1:
        base += 0.02
    if any(char.isdigit() for char in text):
        base += 0.01
    return round(min(base, 0.97), 2)


def _build_claim(
    *,
    state_key: str,
    claim_type: str,
    evidence_type: str,
    text: str,
    source_ids: list[str],
    sentence_index: int,
) -> Claim:
    claim_hash = hashlib.sha256(f"{state_key}|{_normalize(text)}".encode("utf-8")).hexdigest()
    return Claim(
        claim_id=_stable_claim_id_with_sources(state_key, text, source_ids),
        claim_type=claim_type,
        state_key=state_key,
        text=text,
        source_ids=source_ids or [],
        confidence=_claim_confidence(text, source_ids, evidence_type),
        direction=_direction_from_text(text),
        rationale=f"Extracted from {state_key} sentence {sentence_index} via {evidence_type}.",
        evidence_type=evidence_type,
        counterevidence_claim_ids=[],
        counterevidence_source_ids=[],
        claim_hash=claim_hash,
        topic=_topic_from_text(text, claim_type),
    )


def _extract_report_claims(final_state: dict[str, Any], source_registry: dict[str, Any]) -> list[Claim]:
    claims: list[Claim] = []
    for state_key, claim_type, evidence_type in REPORT_CLAIM_SPECS:
        report = final_state.get(state_key)
        if not isinstance(report, str) or not report.strip():
            continue
        for index, sentence in enumerate(_sentences(report), start=1):
            if not _is_fact_sentence(sentence):
                continue
            source_ids, evidence_type = _resolve_evidence(sentence, state_key, source_registry)
            claims.append(
                _build_claim(
                    state_key=state_key,
                    claim_type=claim_type,
                    evidence_type=evidence_type,
                    text=sentence,
                    source_ids=source_ids,
                    sentence_index=index,
                )
            )
    return claims


def _extract_raw_tool_claims(final_state: dict[str, Any], source_registry: dict[str, Any]) -> list[Claim]:
    raw_outputs = final_state.get("raw_tool_outputs")
    if not isinstance(raw_outputs, list):
        return []
    claims: list[Claim] = []
    for index, item in enumerate(raw_outputs, start=1):
        if not isinstance(item, dict):
            continue
        source_id = item.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            continue
        source_ids = [source_id]
        summary = item.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            summary = item.get("output") if isinstance(item.get("output"), str) else item.get("content")
        text = summary if isinstance(summary, str) and summary.strip() else f"Raw tool output from {item.get('tool_name', 'unknown')}"
        claims.append(
            _build_claim(
                state_key="raw_tool_outputs",
                claim_type=RAW_TOOL_CLAIM_SPEC[1],
                evidence_type="explicit_source_reference",
                text=text,
                source_ids=source_ids,
                sentence_index=index,
            )
        )
    return claims


def _attach_counterevidence(claims: list[Claim]) -> list[Claim]:
    by_topic: dict[str, list[Claim]] = {}
    for claim in claims:
        by_topic.setdefault(claim.topic, []).append(claim)

    updated: list[Claim] = []
    for claim in claims:
        counterevidence_ids: list[str] = []
        counterevidence_source_ids: list[str] = []
        for other in by_topic.get(claim.topic, []):
            if other.claim_id == claim.claim_id:
                continue
            if {claim.direction, other.direction} != {"bullish", "bearish"}:
                continue
            counterevidence_ids.append(other.claim_id)
            for source_id in other.source_ids:
                if source_id not in counterevidence_source_ids:
                    counterevidence_source_ids.append(source_id)
        updated.append(
            Claim(
                claim_id=claim.claim_id,
                claim_type=claim.claim_type,
                state_key=claim.state_key,
                text=claim.text,
                source_ids=claim.source_ids,
                confidence=claim.confidence,
                direction=claim.direction,
                rationale=(
                    f"{claim.rationale} Counterevidence found in {len(counterevidence_ids)} opposing claim(s)."
                    if counterevidence_ids
                    else claim.rationale
                ),
                evidence_type=claim.evidence_type,
                counterevidence_claim_ids=sorted(set(counterevidence_ids)),
                counterevidence_source_ids=counterevidence_source_ids,
                claim_hash=claim.claim_hash,
                topic=claim.topic,
            )
        )
    return updated


def extract_claims_from_reports(final_state: dict[str, Any], source_registry: dict[str, Any]) -> list[Claim]:
    sources = source_registry.get("source_objects") if isinstance(source_registry, dict) else []
    if not isinstance(sources, list):
        sources = []
    _ = [item.get("source_id") for item in normalize_source_objects(sources) if item.get("source_id")]
    claims = _extract_report_claims(final_state, source_registry)
    claims.extend(_extract_raw_tool_claims(final_state, source_registry))
    return _attach_counterevidence(claims)


def build_claim_graph(final_state: dict[str, Any], source_registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = source_registry or build_source_registry(final_state)
    claims = extract_claims_from_reports(final_state, registry)
    claim_objects = [
        {
            "claim_id": claim.claim_id,
            "claim_type": claim.claim_type,
            "state_key": claim.state_key,
            "text": claim.text,
            "source_ids": claim.source_ids,
            "confidence": claim.confidence,
            "direction": claim.direction,
            "rationale": claim.rationale,
            "evidence_type": claim.evidence_type,
            "counterevidence_claim_ids": claim.counterevidence_claim_ids,
            "counterevidence_source_ids": claim.counterevidence_source_ids,
            "claim_hash": claim.claim_hash,
            "topic": claim.topic,
        }
        for claim in claims
    ]
    claim_index = {claim["claim_id"]: claim for claim in claim_objects}
    claim_source_ids = sorted({source_id for claim in claims for source_id in claim.source_ids})
    claim_evidence_links = [
        {"claim_id": claim.claim_id, "source_id": source_id, "evidence_type": claim.evidence_type}
        for claim in claims
        for source_id in claim.source_ids
    ]
    direction_counts = {
        direction: sum(1 for claim in claims if claim.direction == direction)
        for direction in ("bullish", "neutral", "bearish")
    }
    enriched_registry = enrich_source_registry_with_claims(registry, claim_objects)
    return {
        "claim_objects": claim_objects,
        "claim_index": claim_index,
        "claim_ids": [claim["claim_id"] for claim in claim_objects],
        "claim_count": len(claim_objects),
        "claim_source_ids": claim_source_ids,
        "claim_evidence_links": claim_evidence_links,
        "source_objects": enriched_registry.get("source_objects", []),
        "source_registry": enriched_registry,
        "claim_summary": {
            "claim_count": len(claim_objects),
            "claim_source_count": len(claim_source_ids),
            "bullish_claim_count": direction_counts["bullish"],
            "neutral_claim_count": direction_counts["neutral"],
            "bearish_claim_count": direction_counts["bearish"],
            "counterevidence_claim_count": sum(1 for claim in claims if claim.counterevidence_claim_ids),
            "source_backed_claim_count": sum(1 for claim in claims if claim.source_ids),
        },
    }
