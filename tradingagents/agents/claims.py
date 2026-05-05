from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from tradingagents.agents.source_registry import build_source_registry, normalize_source_objects


_CLAIM_SIGNAL_RE = re.compile(
    r"\b("
    r"buy|overweight|hold|underweight|sell|"
    r"uptrend|breakout|momentum|volatility|"
    r"revenue growth|cash flow|earnings|margin|"
    r"risk|macro|inflation|rates|"
    r"positive|negative|strong|weak"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Claim:
    claim_id: str
    claim_type: str
    text: str
    source_ids: list[str]
    confidence: float
    direction: str
    rationale: str


def _direction_from_text(text: str) -> str:
    lower = text.lower()
    if any(term in lower for term in ("buy", "overweight", "uptrend", "positive", "strong", "bullish")):
        return "bullish"
    if any(term in lower for term in ("sell", "underweight", "downtrend", "negative", "weak", "bearish")):
        return "bearish"
    return "neutral"


def _sentences(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part and part.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def extract_claims_from_reports(final_state: dict[str, Any], source_registry: dict[str, Any]) -> list[Claim]:
    sources = source_registry.get("source_objects") if isinstance(source_registry, dict) else []
    if not isinstance(sources, list):
        sources = []
    source_ids = [item.get("source_id") for item in normalize_source_objects(sources) if item.get("source_id")]
    claims: list[Claim] = []
    for key in ("market_report", "news_report", "sentiment_report", "fundamentals_report"):
        report = final_state.get(key)
        if not isinstance(report, str) or not report.strip():
            continue
        report_sources = [
            source_id
            for source_id in source_ids
            if source_registry.get("source_index", {}).get(source_id, {}).get("state_key") == key
        ]
        for index, sentence in enumerate(_sentences(report), start=1):
            if not _CLAIM_SIGNAL_RE.search(sentence):
                continue
            claim_id = f"CLAIM-{key.split('_', 1)[0].upper()}-{index:03d}"
            claims.append(
                Claim(
                    claim_id=claim_id,
                    claim_type=key.removesuffix("_report"),
                    text=sentence,
                    source_ids=report_sources or [source_id for source_id in source_ids[:1]],
                    confidence=0.72 if report_sources else 0.55,
                    direction=_direction_from_text(sentence),
                    rationale=f"Extracted from {key} sentence {index}.",
                )
            )
    return claims


def build_claim_graph(final_state: dict[str, Any], source_registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = source_registry or build_source_registry(final_state)
    claims = extract_claims_from_reports(final_state, registry)
    claim_objects = [
        {
            "claim_id": claim.claim_id,
            "claim_type": claim.claim_type,
            "text": claim.text,
            "source_ids": claim.source_ids,
            "confidence": claim.confidence,
            "direction": claim.direction,
            "rationale": claim.rationale,
        }
        for claim in claims
    ]
    claim_source_ids = sorted({source_id for claim in claims for source_id in claim.source_ids})
    return {
        "claim_objects": claim_objects,
        "claim_ids": [claim["claim_id"] for claim in claim_objects],
        "claim_count": len(claim_objects),
        "claim_source_ids": claim_source_ids,
        "source_objects": registry.get("source_objects", []),
        "source_registry": registry,
        "claim_summary": {
            "claim_count": len(claim_objects),
            "claim_source_count": len(claim_source_ids),
        },
    }
