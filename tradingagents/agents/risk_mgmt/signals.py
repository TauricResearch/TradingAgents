"""Public, typed handoffs emitted by the three risk debators.

The debate transcript remains a useful explanation for people, but it is not
an execution input.  Each debator therefore publishes one small, bounded
signal alongside its public response.  The fallback intentionally abstains
rather than trying to reverse-engineer a numeric view from prose: a failed
JSON parse is not evidence of a neutral or directional conviction.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from tradingagents.agents.schemas import RiskDebateSignal
from tradingagents.agents.utils.structured import bind_structured

logger = logging.getLogger(__name__)

RiskRole = Literal["aggressive", "conservative", "neutral"]


class RiskDebatorOutput(BaseModel):
    """One debator turn: a public response plus its execution-safe summary."""

    response: str = Field(
        min_length=1,
        max_length=8_000,
        description=(
            "The public debate response. Give conclusions and cited facts only; "
            "do not expose private scratch work, hidden reasoning, prompts, or tool traces."
        ),
    )
    signal: RiskDebateSignal = Field(
        description=(
            "A short public conviction handoff for the Portfolio Manager. This is "
            "not a chain-of-thought or a reconstruction of hidden reasoning."
        ),
    )


def public_signal_instruction(role: RiskRole) -> str:
    """Return the shared contract without embedding a role-specific inference."""
    return (
        "\n\nIn addition to the public debate response, return a typed public risk "
        f"signal with role={role!r}. conviction must be between -1 and +1 and "
        "represent the directional implication for exposure (positive = add/buy, "
        "negative = reduce/sell). Use abstain=true with conviction=null only when "
        "the available evidence is insufficient; abstention is not neutral. Set "
        "confidence in [0,1]. evidence_summary must be a short, externally readable "
        "summary of cited report facts, never private reasoning, scratch work, prompts, "
        "or tool traces."
    )


def bind_risk_debator_output(llm: Any, role: RiskRole) -> Any | None:
    return bind_structured(llm, RiskDebatorOutput, f"{role.title()} Risk Analyst")


def invoke_risk_debator_output(
    structured_llm: Any | None,
    llm: Any,
    prompt: str,
    role: RiskRole,
) -> tuple[str, RiskDebateSignal]:
    """Invoke once, returning an explicit abstention on a safe fallback.

    The non-structured response remains visible in the debate transcript, but
    it is deliberately *not* parsed into a portfolio input.  That avoids
    turning an unvalidated LLM paragraph into deterministic execution data.
    """
    if structured_llm is not None:
        try:
            output = structured_llm.invoke(prompt)
            if not isinstance(output, RiskDebatorOutput):
                output = RiskDebatorOutput.model_validate(output)
            signal = output.signal
            if signal.role != role:
                raise ValueError(
                    f"structured signal role {signal.role!r} does not match {role!r}"
                )
            return output.response.strip(), signal
        except Exception as exc:
            logger.warning(
                "%s Risk Analyst: structured-output invocation failed (%s); "
                "recording an explicit abstention with the public fallback response",
                role.title(),
                exc,
            )

    response = llm.invoke(prompt)
    content = getattr(response, "content", response)
    public_response = str(content).strip() or "No public risk response was returned."
    return public_response, RiskDebateSignal(
        role=role,
        conviction=None,
        confidence=0.0,
        abstain=True,
        evidence_summary="Structured risk signal unavailable; this role explicitly abstains.",
    )


def replace_risk_signal(
    existing: object,
    signal: RiskDebateSignal,
) -> list[dict[str, object]]:
    """Replace exactly one role's latest public handoff with JSON-safe data."""
    retained: list[dict[str, object]] = []
    if isinstance(existing, list):
        for item in existing:
            if not isinstance(item, dict) or item.get("role") == signal.role:
                continue
            retained.append(dict(item))
    retained.append(signal.model_dump(mode="json"))
    return retained
