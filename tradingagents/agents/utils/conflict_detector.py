"""Cross-factor conflict detection between analyst signals (P0.1).

Runs after the four analysts finish, before the bull/bear debate. The LLM only
fills a narrow, structured task — one FactorSignal per factor extracted from the
prose reports. The cross-factor divergence scoring is pure Python, so a real
conflict cannot be talked out of being flagged by persuasive narrative.

The output is written to state["conflict_report"] and consumed by the bull/bear
researchers and the Portfolio Manager. The node is fail-safe: any error yields an
empty report with an explanatory note, so the pipeline never blocks.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

__all__ = [
    "FactorSignal",
    "CrossFactorConflict",
    "ConflictReport",
    "detect_conflicts",
    "format_conflict_report_for_prompt",
    "create_conflict_detector",
]

_FACTORS = (
    "trend",
    "volume",
    "sentiment",
    "options_positioning",
    "fundamentals_quality",
    "news_tone",
)

# Pairs whose opposite-direction reading is a meaningful cross-factor divergence.
_CONFLICT_PAIRS = (
    ("trend", "volume"),
    ("trend", "sentiment"),
    ("news_tone", "sentiment"),
    ("trend", "options_positioning"),
    ("fundamentals_quality", "sentiment"),
    ("news_tone", "options_positioning"),
)


class FactorSignal(BaseModel):
    factor: Literal[
        "trend",
        "volume",
        "sentiment",
        "options_positioning",
        "fundamentals_quality",
        "news_tone",
    ]
    direction: Literal["bullish", "bearish", "neutral", "unavailable"]
    strength: float = Field(ge=0.0, le=1.0, description="0 = weak/uncertain, 1 = strong.")
    source_report: Literal["market", "news", "sentiment", "fundamentals"]
    excerpt: str = Field(description="Short justification quoted/paraphrased from the report.")


class _FactorSignalList(BaseModel):
    """Wrapper so providers that need a top-level object can emit a list field."""

    signals: list[FactorSignal] = Field(default_factory=list)


class CrossFactorConflict(BaseModel):
    factor_a: str
    factor_b: str
    severity: float = Field(ge=0.0, le=1.0)
    description: str


class ConflictReport(BaseModel):
    signals: list[FactorSignal] = Field(default_factory=list)
    conflicts: list[CrossFactorConflict] = Field(default_factory=list)
    overall_alignment: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="1.0 = all available signals agree; lower = more divergence.",
    )
    notes: list[str] = Field(default_factory=list)


_EXTRACTION_PROMPT = """You extract structured factor signals from analyst reports. Do NOT take a side or trade.

For each of these factors, emit exactly one FactorSignal: trend, volume, sentiment, options_positioning, fundamentals_quality, news_tone.
- direction: bullish / bearish / neutral / unavailable. Use "unavailable" if the reports do not address the factor or the underlying data was missing (e.g. options chain returned a NOTICE).
- strength: 0-1, how strongly the report supports that direction.
- source_report: which report the signal came from (market / news / sentiment / fundamentals).
- excerpt: a short phrase or number from the report that justifies it.

Report only what the text says. Do not infer a direction the report did not state.

Market report:
{market_report}

News report:
{news_report}

Sentiment report:
{sentiment_report}

Fundamentals report:
{fundamentals_report}
"""


def _disallows_structured_output(llm) -> bool:
    model = (getattr(llm, "model_name", None) or getattr(llm, "model", "") or "").lower()
    if model.startswith("deepseek-") or model == "deepseek-chat":
        return True
    extra_body = getattr(llm, "extra_body", None) or {}
    thinking = extra_body.get("thinking") if isinstance(extra_body, dict) else None
    return isinstance(thinking, dict) and thinking.get("type") == "enabled"


def _parse_signal_list_from_text(text: str) -> list[FactorSignal]:
    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        try:
            if isinstance(data, dict) and "signals" in data:
                return _FactorSignalList.model_validate(data).signals
            if isinstance(data, list):
                return _FactorSignalList.model_validate({"signals": data}).signals
        except Exception:
            continue
    return []


def _extract_signals(
    llm,
    market_report: str,
    news_report: str,
    sentiment_report: str,
    fundamentals_report: str,
) -> list[FactorSignal]:
    prompt = _EXTRACTION_PROMPT.format(
        market_report=(market_report or "(none)")[:4000],
        news_report=(news_report or "(none)")[:4000],
        sentiment_report=(sentiment_report or "(none)")[:4000],
        fundamentals_report=(fundamentals_report or "(none)")[:4000],
    )

    if not _disallows_structured_output(llm):
        try:
            structured = llm.with_structured_output(_FactorSignalList)
            return structured.invoke(prompt).signals
        except Exception as exc:
            logger.warning("conflict_detector: structured extraction failed (%s); trying free-text JSON", exc)

    try:
        response = llm.invoke(prompt)
        content = getattr(response, "content", response)
        return _parse_signal_list_from_text(str(content))
    except Exception as exc:
        logger.warning("conflict_detector: free-text extraction failed (%s); returning no signals", exc)
        return []


def _score_conflicts(signals: list[FactorSignal]) -> tuple[list[CrossFactorConflict], float]:
    by_factor = {s.factor: s for s in signals}
    conflicts: list[CrossFactorConflict] = []
    evaluable_pairs = 0
    for a, b in _CONFLICT_PAIRS:
        sa, sb = by_factor.get(a), by_factor.get(b)
        if not sa or not sb:
            continue
        if sa.direction == "unavailable" or sb.direction == "unavailable":
            continue
        evaluable_pairs += 1
        if {sa.direction, sb.direction} == {"bullish", "bearish"}:
            severity = round((sa.strength + sb.strength) / 2.0, 3)
            conflicts.append(
                CrossFactorConflict(
                    factor_a=a,
                    factor_b=b,
                    severity=severity,
                    description=(
                        f"{a}={sa.direction}({sa.strength:.2f}) vs "
                        f"{b}={sb.direction}({sb.strength:.2f})"
                    ),
                )
            )
    alignment = 1.0 - len(conflicts) / evaluable_pairs if evaluable_pairs else 1.0
    return conflicts, round(alignment, 3)


def detect_conflicts(
    market_report: str,
    news_report: str,
    sentiment_report: str,
    fundamentals_report: str,
    anchors: Optional[dict],
    llm,
) -> ConflictReport:
    """Extract factor signals via the LLM, then mechanically score divergences."""
    try:
        signals = _extract_signals(
            llm, market_report, news_report, sentiment_report, fundamentals_report
        )
    except Exception as exc:  # belt-and-suspenders; _extract_signals already guards
        logger.warning("conflict_detector: extraction raised (%s)", exc)
        return ConflictReport(notes=[f"conflict detection unavailable: {exc}"])

    conflicts, alignment = _score_conflicts(signals)
    notes: list[str] = []

    # Deterministic ORCL-style gate: a bullish trend read on shrinking volume is a
    # hard divergence the narrative tends to wave away. Flag it from anchors directly.
    if anchors:
        vr = anchors.get("volume_ratio")
        by_factor = {s.factor: s for s in signals}
        trend_sig = by_factor.get("trend")
        if vr is not None and vr < 0.7 and trend_sig and trend_sig.direction == "bullish":
            notes.append(
                f"BULLISH-TREND-ON-SHRINKING-VOLUME: volume_ratio={vr:.2f} (<0.7) "
                f"contradicts the bullish trend read from {trend_sig.source_report}_report. "
                "Treat a low-volume rally as unconfirmed."
            )

    return ConflictReport(
        signals=signals,
        conflicts=conflicts,
        overall_alignment=alignment,
        notes=notes,
    )


def format_conflict_report_for_prompt(report: Optional[dict | ConflictReport]) -> str:
    """Render a ConflictReport (dict or model) into a prompt block. Empty string if absent."""
    if report is None:
        return ""
    if isinstance(report, dict):
        try:
            report = ConflictReport.model_validate(report)
        except Exception:
            return ""
    if not report.signals and not report.conflicts and not report.notes:
        return ""

    lines = ["\n\n**Cross-factor conflict check (computed before this step):**"]
    lines.append(f"- overall_alignment: {report.overall_alignment:.2f} (1.0 = all factors agree)")
    if report.conflicts:
        for c in report.conflicts:
            lines.append(f"- CONFLICT: {c.description} (severity={c.severity:.2f})")
    else:
        lines.append("- no opposite-direction factor pairs detected")
    for note in report.notes:
        lines.append(f"- NOTE: {note}")
    lines.append(
        "You MUST explicitly address each CONFLICT and NOTE above in your rationale "
        "before committing to a direction; do not let one factor silently override a contradicting one."
    )
    return "\n".join(lines)


def create_conflict_detector(llm):
    """Graph-node factory. Computes short-term anchors, runs conflict detection."""

    def conflict_detector_node(state) -> dict:
        # Lazy import keeps the heavy portfolio_state_manager dependency off module load.
        try:
            from tradingagents.agents.managers.portfolio_state_manager import (
                _compute_short_term_market_anchors,
            )
            anchors = _compute_short_term_market_anchors(
                state["company_of_interest"], state["trade_date"]
            )
        except Exception as exc:
            logger.warning("conflict_detector: anchor computation failed (%s)", exc)
            anchors = None

        report = detect_conflicts(
            market_report=state.get("market_report", ""),
            news_report=state.get("news_report", ""),
            sentiment_report=state.get("sentiment_report", ""),
            fundamentals_report=state.get("fundamentals_report", ""),
            anchors=anchors,
            llm=llm,
        )
        return {"conflict_report": report.model_dump()}

    return conflict_detector_node
