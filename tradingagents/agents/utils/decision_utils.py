from __future__ import annotations

import re
from typing import Any, Iterable

CANONICAL_RATINGS = ("BUY", "OVERWEIGHT", "HOLD", "UNDERWEIGHT", "SELL")
_RATING_PATTERN = re.compile(
    r"\b(BUY|OVERWEIGHT|HOLD|UNDERWEIGHT|SELL)\b",
    re.IGNORECASE,
)


def extract_rating(text: str) -> str | None:
    match = _RATING_PATTERN.search(str(text or ""))
    if not match:
        return None
    return match.group(1).upper()


def _normalize_report_text(rating: str, rating_source: str, report_text: str) -> str:
    body = str(report_text or "").strip() or "No narrative provided."
    return (
        "## Normalized Portfolio Decision\n"
        f"- Rating: {rating}\n"
        f"- Rating Source: {rating_source}\n\n"
        f"{body}"
    )


def build_structured_decision(
    text: str,
    *,
    fallback_candidates: Iterable[tuple[str, str]] = (),
    default_rating: str = "HOLD",
    peer_context_mode: str = "UNSPECIFIED",
    context_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    rating_source = "direct"
    rating = extract_rating(text)
    source_text = str(text or "")

    if rating is None:
        for candidate_name, candidate_text in fallback_candidates:
            rating = extract_rating(candidate_text)
            if rating is not None:
                rating_source = candidate_name
                source_text = str(candidate_text or "")
                warnings.append(f"rating_inferred_from:{candidate_name}")
                break

    if rating is None:
        rating = str(default_rating or "HOLD").upper()
        rating_source = "default"
        warnings.append("rating_defaulted")

    usage = context_usage or {}
    hold_subtype = "UNSPECIFIED" if rating == "HOLD" else "N/A"

    return {
        "rating": rating,
        "hold_subtype": hold_subtype,
        "rating_source": rating_source,
        "report_text": _normalize_report_text(rating, rating_source, source_text),
        "warnings": warnings,
        "portfolio_context_used": bool(usage.get("portfolio_context")),
        "peer_context_used": bool(usage.get("peer_context")),
        "peer_context_mode": str(peer_context_mode or "UNSPECIFIED"),
    }
