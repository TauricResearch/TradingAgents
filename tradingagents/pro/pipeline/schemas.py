"""Structured-output schemas for pipeline LLM nodes.

Like EvidenceDraft, these are deliberately small: pipeline LLMs argue,
critique, and decide — every number they discuss was computed upstream,
and everything they output is validated at the boundary.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DebateTurn(BaseModel):
    """One debater's argument in the bull/bear exchange."""

    argument: str = Field(
        min_length=1,
        description=(
            "Your case, 2-5 sentences, engaging the opponent's last argument "
            "directly. Reference evidence by agent id (e.g. 'rsi', 'dollar_index'); "
            "cite only evidence shown to you."
        ),
    )
    cited_agent_ids: list[str] = Field(
        default_factory=list,
        description="Agent ids of the evidence items your argument rests on.",
    )
    confidence: int = Field(ge=0, le=100, description="Strength of your side after this turn.")


class CriticReport(BaseModel):
    """Adversarial audit of the debate against the evidence record."""

    verdict: Literal["pass", "fail"] = Field(
        description=(
            "'fail' only for disqualifying defects: arguments citing evidence "
            "that does not exist, direction claims contradicting the cited "
            "evidence, or a debate that ignored the strongest opposing evidence."
        ),
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Each defect found, one sentence each, naming the offending speaker.",
    )


class ReflectionNote(BaseModel):
    """Pre-decision reflection: falsifiability check before the judge rules."""

    weaknesses: str = Field(
        min_length=1,
        description="The 2-3 weakest links in the prevailing thesis, from the record.",
    )
    invalidation: str = Field(
        min_length=1,
        description="What observable change would invalidate the thesis.",
    )


class JudgeVerdict(BaseModel):
    """The judge's ruling after debate, critique, and reflection."""

    action: Literal["BUY", "SELL", "HOLD"] = Field(
        description=(
            "Your ruling. Commit to BUY or SELL when one side's evidence "
            "clearly carried the debate; HOLD when genuinely balanced or when "
            "the vote tally and debate record conflict."
        ),
    )
    confidence: int = Field(ge=0, le=100)
    rationale: str = Field(
        min_length=1,
        description=(
            "2-4 sentences: which arguments decided it, which you discounted "
            "and why, referencing speakers and agent ids from the record."
        ),
    )
