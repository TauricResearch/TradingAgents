"""Deterministic source-alignment projection for evidence and debate views."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

AlignmentLabel = Literal["Bullish", "Bearish", "Tight alignment", "Wide divergence", "Mixed", "No coverage"]


@dataclass(frozen=True)
class SourceSignal:
    source_id: str
    score: float

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        if not -1.0 <= self.score <= 1.0:
            raise ValueError("score must be in [-1, 1]")


@dataclass(frozen=True)
class SourceAlignment:
    label: AlignmentLabel
    source_count: int
    bullish_percent: float
    bearish_percent: float
    mean_score: float | None
    score_range: float | None


def project_source_alignment(signals: Iterable[SourceSignal]) -> SourceAlignment:
    """Classify consensus from each source's normalized final signal.

    Classification is intentionally transparent: directional labels require
    directional agreement; otherwise a tight range, wide range, or mixed
    label exposes the disagreement to downstream agents and the UI.
    """
    values = list(signals)
    if not values:
        return SourceAlignment("No coverage", 0, 0.0, 0.0, None, None)
    scores = [signal.score for signal in values]
    count = len(scores)
    bullish = sum(score > 0 for score in scores) / count
    bearish = sum(score < 0 for score in scores) / count
    mean = sum(scores) / count
    spread = max(scores) - min(scores)
    if all(score > 0 for score in scores) and mean >= 0.35:
        label: AlignmentLabel = "Bullish"
    elif all(score < 0 for score in scores) and mean <= -0.35:
        label = "Bearish"
    elif spread <= 0.25:
        label = "Tight alignment"
    elif spread >= 0.8:
        label = "Wide divergence"
    else:
        label = "Mixed"
    return SourceAlignment(label, count, bullish, bearish, mean, spread)


def source_alignment_from_ledger(ledger: Any) -> SourceAlignment | None:
    """Project a directional source-alignment view from an evidence ledger.

    Returns ``None`` when the ledger has no evidence records carrying an
    explicit ``direction_score`` in [-1, 1].  Credibility, provenance, and
    source counts are not directional signals, so this refuses to manufacture
    bullish/bearish alignment from them; a compatible data source must provide
    the score explicitly.  Shared by the observability projection and the
    debate prompt so the two views never diverge.
    """
    if not isinstance(ledger, Mapping):
        return None
    evidence = ledger.get("evidence")
    if not isinstance(evidence, (list, tuple)):
        return None
    signals: list[SourceSignal] = []
    seen_ids: set[str] = set()
    for index, record in enumerate(evidence):
        if not isinstance(record, Mapping):
            continue
        score = record.get("direction_score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            continue
        source_id = str(
            record.get("source_provider")
            or record.get("evidence_id")
            or f"source-{index}"
        ).strip()
        if not source_id or source_id in seen_ids:
            continue
        try:
            signals.append(SourceSignal(source_id, float(score)))
        except ValueError:
            continue
        seen_ids.add(source_id)
    if not signals:
        return None
    return project_source_alignment(signals)


def render_source_alignment_summary(ledger: Any) -> str | None:
    """Render a compact, prompt-safe summary of source alignment from a ledger.

    Returns None when no directional evidence is available, so callers can
    omit the section entirely rather than advertising an empty signal.  The
    text is deliberately factual (label, counts, mean, range) and carries no
    model reasoning.
    """
    alignment = source_alignment_from_ledger(ledger)
    if alignment is None:
        return None
    parts = [
        f"label={alignment.label}",
        f"sources={alignment.source_count}",
    ]
    if alignment.mean_score is not None:
        parts.append(f"mean={alignment.mean_score:+.2f}")
    if alignment.score_range is not None:
        parts.append(f"range={alignment.score_range:.2f}")
    parts.append(f"bullish={round(alignment.bullish_percent * 100)}%")
    parts.append(f"bearish={round(alignment.bearish_percent * 100)}%")
    return ", ".join(parts)
