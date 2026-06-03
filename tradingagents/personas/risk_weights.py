"""Persona-weighted risk-debate formatter."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from tradingagents.personas.loader import Persona


def _section(label: str, body: str, weight: Optional[float]) -> str:
    body = (body or "").strip() or "(no entries)"
    if weight is None:
        return f"### {label}\n{body}"
    return f"### {label} (weight {weight:.2f})\n{body}"


def format_weighted_risk_debate(
    state: Mapping[str, Any],
    persona: Optional[Persona],
) -> str:
    weights = persona.risk_debate.weights if persona is not None else {}
    return (
        _section(
            "Aggressive",
            state.get("aggressive_history", ""),
            weights.get("aggressive"),
        )
        + "\n\n"
        + _section(
            "Conservative",
            state.get("conservative_history", ""),
            weights.get("conservative"),
        )
        + "\n\n"
        + _section(
            "Neutral",
            state.get("neutral_history", ""),
            weights.get("neutral"),
        )
    )
