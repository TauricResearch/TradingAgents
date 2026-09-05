"""Renderers and legacy adapters for validated agent artifacts."""

from __future__ import annotations

import re
from datetime import date

from .agent_contracts import (
    AgentOutputEnvelope,
    AgentOutputSection,
    AgentOutputType,
    AnalystNote,
    ConfidenceLevel,
    EvidenceRef,
    InvestmentThesis,
    TradeDirection,
    TradeHorizon,
    TradeSignal,
)

_RATINGS_5_TIER = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
_RATING_SET = {rating.lower() for rating in _RATINGS_5_TIER}
_RATING_LABEL_RE = re.compile(r"rating.*?[:\-][\s*]*(\w+)", re.IGNORECASE)


def render_evidence(refs: list[EvidenceRef]) -> str:
    """Render evidence references in a compact, report-friendly shape."""

    if not refs:
        return "No structured evidence references."

    lines = ["| Source | As Of | Confidence | Description |", "| --- | --- | --- | --- |"]
    for ref in refs:
        lines.append(
            "| "
            + " | ".join(
                [
                    ref.source_id,
                    ref.as_of_date.isoformat(),
                    f"{ref.confidence:.0%}",
                    _single_line(ref.description),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def render_analyst_note(note: AnalystNote) -> str:
    """Render an AnalystNote as deterministic markdown."""

    parts = [
        f"## {note.analyst_role} Note: {note.symbol}",
        "",
        f"**As Of:** {note.as_of_date.isoformat()}",
        f"**Confidence:** {note.confidence.value}",
        "",
        "### Summary",
        note.summary,
        "",
        "### Evidence",
        render_evidence(note.evidence),
    ]
    if note.risks:
        parts.extend(["", "### Risks", *[f"- {risk}" for risk in note.risks]])
    return "\n".join(parts)


def render_investment_thesis(thesis: InvestmentThesis) -> str:
    """Render an InvestmentThesis as deterministic markdown."""

    parts = [
        f"## Investment Thesis: {thesis.symbol}",
        "",
        f"**As Of:** {thesis.as_of_date.isoformat()}",
        f"**Confidence:** {thesis.confidence:.0%}",
        "",
        "### Base Case",
        thesis.base_case,
        "",
        "### Bull Case",
        thesis.bull_case,
        "",
        "### Bear Case",
        thesis.bear_case,
    ]
    if thesis.catalysts:
        parts.extend(["", "### Catalysts", *[f"- {item}" for item in thesis.catalysts]])
    if thesis.disconfirming_evidence:
        parts.extend(
            [
                "",
                "### Disconfirming Evidence",
                *[f"- {item}" for item in thesis.disconfirming_evidence],
            ]
        )
    parts.extend(["", "### Evidence", render_evidence(thesis.evidence)])
    return "\n".join(parts)


def render_trade_signal(signal: TradeSignal) -> str:
    """Render a TradeSignal as deterministic markdown."""

    parts = [
        f"## Trade Signal: {signal.symbol}",
        "",
        f"**As Of:** {signal.as_of_date.isoformat()}",
        f"**Direction:** {signal.direction.value}",
        f"**Horizon:** {signal.horizon.value}",
        f"**Confidence:** {signal.confidence:.0%}",
    ]
    if signal.proposed_position_pct is not None:
        parts.append(f"**Proposed Position:** {signal.proposed_position_pct:.1%}")
    if signal.expected_return_pct is not None:
        parts.append(f"**Expected Return:** {signal.expected_return_pct:.1%}")
    if signal.stop_loss_pct is not None:
        parts.append(f"**Stop Loss:** {signal.stop_loss_pct:.1%}")

    parts.extend(["", "### Rationale", signal.rationale])
    if signal.invalidation_triggers:
        parts.extend(
            ["", "### Invalidation Triggers", *[f"- {item}" for item in signal.invalidation_triggers]]
        )
    parts.extend(["", "### Evidence", render_evidence(signal.evidence)])
    return "\n".join(parts)


def render_agent_output(output: AgentOutputEnvelope) -> str:
    """Render one structured agent output for reports and cockpit previews."""

    parts = [
        f"### {output.agent_role}: {output.headline}",
        "",
        f"**Agent ID:** `{output.agent_id}`",
        f"**Type:** {output.output_type.value}",
        f"**As Of:** {output.as_of_date.isoformat()}",
        f"**Confidence:** {output.confidence.value}",
        "",
        output.summary,
    ]

    for section in output.sections:
        parts.extend(["", f"#### {section.title}"])
        if section.summary:
            parts.extend(["", section.summary])
        if section.bullets:
            parts.extend(["", *[f"- {item}" for item in section.bullets]])
        if section.evidence:
            parts.extend(["", render_evidence(section.evidence)])

    if output.risks:
        parts.extend(["", "#### Risks / Watch Items", *[f"- {risk}" for risk in output.risks]])

    parts.extend(["", "#### Evidence", render_evidence(output.evidence)])
    return "\n".join(parts)


def render_agent_outputs(outputs: list[AgentOutputEnvelope]) -> str:
    """Render multiple agent outputs in cockpit/report order."""

    if not outputs:
        return "No structured agent outputs available."
    ordered = sorted(outputs, key=lambda item: (item.as_of_date, item.agent_role, item.agent_id))
    return "\n\n".join(render_agent_output(output) for output in ordered)


def agent_output_from_analyst_note(
    note: AnalystNote,
    *,
    agent_id: str | None = None,
) -> AgentOutputEnvelope:
    """Wrap an AnalystNote in the standard agent-output envelope."""

    sections = [
        AgentOutputSection(
            title="Summary",
            summary=note.summary,
            evidence=note.evidence,
        )
    ]
    if note.risks:
        sections.append(AgentOutputSection(title="Risks", bullets=note.risks))

    return AgentOutputEnvelope(
        symbol=note.symbol,
        as_of_date=note.as_of_date,
        agent_id=agent_id or _slug_agent_id(note.analyst_role),
        agent_role=note.analyst_role,
        output_type=AgentOutputType.ANALYST_NOTE,
        headline=f"{note.analyst_role} note for {note.symbol}",
        summary=note.summary,
        sections=sections,
        evidence=note.evidence,
        risks=note.risks,
        confidence=note.confidence,
        payload=note,
        metadata={"source_artifact": "AnalystNote"},
    )


def agent_output_from_investment_thesis(
    thesis: InvestmentThesis,
    *,
    agent_id: str = "research-manager",
    agent_role: str = "Research Manager",
) -> AgentOutputEnvelope:
    """Wrap an InvestmentThesis in the standard agent-output envelope."""

    sections = [
        AgentOutputSection(title="Base Case", summary=thesis.base_case, evidence=thesis.evidence),
        AgentOutputSection(title="Bull Case", summary=thesis.bull_case),
        AgentOutputSection(title="Bear Case", summary=thesis.bear_case),
    ]
    if thesis.catalysts:
        sections.append(AgentOutputSection(title="Catalysts", bullets=thesis.catalysts))
    if thesis.disconfirming_evidence:
        sections.append(
            AgentOutputSection(
                title="Disconfirming Evidence",
                bullets=thesis.disconfirming_evidence,
            )
        )

    return AgentOutputEnvelope(
        symbol=thesis.symbol,
        as_of_date=thesis.as_of_date,
        agent_id=agent_id,
        agent_role=agent_role,
        output_type=AgentOutputType.INVESTMENT_THESIS,
        headline=f"Investment thesis for {thesis.symbol}",
        summary=_first_sentence(thesis.base_case),
        sections=sections,
        evidence=thesis.evidence,
        risks=thesis.disconfirming_evidence,
        confidence=_confidence_level_from_score(thesis.confidence),
        payload=thesis,
        metadata={"source_artifact": "InvestmentThesis", "confidence_score": thesis.confidence},
    )


def agent_output_from_trade_signal(
    signal: TradeSignal,
    *,
    agent_id: str = "portfolio-manager",
    agent_role: str = "Portfolio Manager",
) -> AgentOutputEnvelope:
    """Wrap a TradeSignal in the standard agent-output envelope."""

    bullets = [
        f"Direction: {signal.direction.value}",
        f"Horizon: {signal.horizon.value}",
        f"Confidence: {signal.confidence:.0%}",
    ]
    if signal.proposed_position_pct is not None:
        bullets.append(f"Proposed position: {signal.proposed_position_pct:.1%}")
    if signal.expected_return_pct is not None:
        bullets.append(f"Expected return: {signal.expected_return_pct:.1%}")
    if signal.stop_loss_pct is not None:
        bullets.append(f"Stop loss: {signal.stop_loss_pct:.1%}")

    sections = [
        AgentOutputSection(title="Decision", bullets=bullets, evidence=signal.evidence),
        AgentOutputSection(title="Rationale", summary=signal.rationale),
    ]
    if signal.invalidation_triggers:
        sections.append(
            AgentOutputSection(
                title="Invalidation Triggers",
                bullets=signal.invalidation_triggers,
            )
        )

    return AgentOutputEnvelope(
        symbol=signal.symbol,
        as_of_date=signal.as_of_date,
        agent_id=agent_id,
        agent_role=agent_role,
        output_type=AgentOutputType.TRADE_SIGNAL,
        headline=f"{signal.direction.value.title()} signal for {signal.symbol}",
        summary=(
            f"{signal.direction.value.title()} / {signal.horizon.value} signal "
            f"with {signal.confidence:.0%} confidence."
        ),
        sections=sections,
        evidence=signal.evidence,
        risks=signal.invalidation_triggers,
        confidence=_confidence_level_from_score(signal.confidence),
        payload=signal,
        metadata={"source_artifact": "TradeSignal", "confidence_score": signal.confidence},
    )


def analyst_note_from_legacy_report(
    *,
    symbol: str,
    analyst_role: str,
    as_of_date: date,
    report: str,
    evidence: list[EvidenceRef] | None = None,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
) -> AnalystNote:
    """Wrap a legacy analyst markdown report as an AnalystNote."""

    summary = _required_text(report, "legacy analyst report")
    return AnalystNote(
        symbol=symbol,
        analyst_role=analyst_role,
        as_of_date=as_of_date,
        summary=summary,
        evidence=evidence or [],
        confidence=confidence,
    )


def investment_thesis_from_legacy_plan(
    *,
    symbol: str,
    as_of_date: date,
    plan: str,
    evidence: list[EvidenceRef] | None = None,
    confidence: float = 0.5,
) -> InvestmentThesis:
    """Convert a legacy research-manager plan into a conservative thesis."""

    text = _required_text(plan, "legacy investment plan")
    rationale = _extract_markdown_field(text, "Rationale") or text
    actions = _extract_markdown_field(text, "Strategic Actions")

    base_case = rationale
    if actions:
        base_case = f"{base_case}\n\nStrategic actions: {actions}"

    return InvestmentThesis(
        symbol=symbol,
        as_of_date=as_of_date,
        base_case=base_case,
        bull_case="Not separately available in the legacy research plan.",
        bear_case="Not separately available in the legacy research plan.",
        evidence=evidence or [],
        confidence=confidence,
    )


def trade_signal_from_legacy_decision(
    *,
    symbol: str,
    as_of_date: date,
    decision_text: str,
    evidence: list[EvidenceRef] | None = None,
    confidence: float = 0.5,
    horizon: TradeHorizon = TradeHorizon.MEDIUM,
) -> TradeSignal:
    """Convert legacy final decision markdown into a TradeSignal."""

    text = _required_text(decision_text, "legacy final decision")
    rating = _parse_legacy_rating(text)
    direction = trade_direction_from_rating(rating)
    position_pct = _extract_labeled_percent(text, "Position Sizing")
    if position_pct is None:
        position_pct = _extract_labeled_percent(text, "Proposed Position")
    expected_return = _extract_labeled_percent(text, "Expected Return")
    stop_loss = _extract_labeled_percent(text, "Stop Loss")

    return TradeSignal(
        symbol=symbol,
        as_of_date=as_of_date,
        direction=direction,
        horizon=horizon,
        confidence=confidence,
        rationale=text,
        proposed_position_pct=position_pct,
        expected_return_pct=expected_return,
        stop_loss_pct=stop_loss,
        evidence=evidence or [],
        invalidation_triggers=_extract_invalidation_triggers(text),
    )


def trade_direction_from_rating(rating: str) -> TradeDirection:
    """Map the legacy 5-tier portfolio rating to a 3-way trade direction."""

    normalized = rating.strip().lower()
    if normalized in {"buy", "overweight"}:
        return TradeDirection.BUY
    if normalized in {"sell", "underweight"}:
        return TradeDirection.SELL
    return TradeDirection.HOLD


def _parse_legacy_rating(text: str, default: str = "Hold") -> str:
    for line in text.splitlines():
        match = _RATING_LABEL_RE.search(line)
        if match and match.group(1).lower() in _RATING_SET:
            return match.group(1).capitalize()

    for line in text.splitlines():
        for word in line.lower().split():
            cleaned = word.strip("*:.,")
            if cleaned in _RATING_SET:
                return cleaned.capitalize()

    return default


def _extract_markdown_field(text: str, label: str) -> str | None:
    pattern = re.compile(
        rf"^\s*\**{re.escape(label)}\**\s*:\s*(.+?)(?=\n\s*\**[A-Z][A-Za-z ]+\**\s*:|\Z)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1).strip()


def _extract_labeled_percent(text: str, label: str) -> float | None:
    field = _extract_markdown_field(text, label)
    if not field:
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", field)
    if not match:
        return None
    value = float(match.group(1)) / 100.0
    return max(0.0, min(1.0, value))


def _extract_invalidation_triggers(text: str) -> list[str]:
    field = _extract_markdown_field(text, "Invalidation Triggers")
    if not field:
        return []
    triggers = []
    for line in field.splitlines():
        cleaned = line.strip().lstrip("-*").strip()
        if cleaned:
            triggers.append(cleaned)
    return triggers


def _required_text(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{label} must be non-empty")
    return cleaned


def _single_line(value: str) -> str:
    return " ".join(value.split())


def _slug_agent_id(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return cleaned.strip("-") or "agent"


def _confidence_level_from_score(score: float) -> ConfidenceLevel:
    if score >= 0.75:
        return ConfidenceLevel.HIGH
    if score < 0.4:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.MEDIUM


def _first_sentence(value: str, max_length: int = 220) -> str:
    text = _single_line(value)
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    if len(sentence) <= max_length:
        return sentence
    return sentence[: max_length - 3].rstrip() + "..."
