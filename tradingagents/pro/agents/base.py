"""EvidenceAgent: the single runtime shared by every Pro evidence agent.

One class, many AgentSpecs. The LLM's job is deliberately small: given a
deterministic data block, return claim + direction + confidence through
structured output. Attribution (data_refs, sources) is attached by code
from the rendered context (ADR-0015), and an agent whose context came back
empty abstains — it returns None instead of unsupported opinion.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from importlib import resources
from typing import Literal

from pydantic import BaseModel, Field

from tradingagents.contracts import AgentEvidence, Direction, MarketSnapshot, MetricReading
from tradingagents.pro.agents.rendering import render_context
from tradingagents.pro.agents.specs import AgentSpec

logger = logging.getLogger(__name__)


class EvidenceDraft(BaseModel):
    """The only thing the LLM is asked to produce."""

    claim: str = Field(
        min_length=1,
        description=(
            "One to three sentences stating your read of the data shown to you. "
            "Reference only values present in the data block."
        ),
    )
    direction: Literal["bullish", "bearish", "neutral"] = Field(
        description="Directional implication of your claim for the asset."
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description=(
            "0-100. Below 35 = weak/insufficient signal, 35-65 = moderate, "
            "above 65 = strong, corroborated signal. Missing inputs lower confidence."
        ),
    )


def load_team_template(team_value: str) -> str:
    """Load a team prompt template from the versioned prompts/ directory."""
    return (
        resources.files("tradingagents.pro.agents")
        .joinpath("prompts", f"{team_value}_team.md")
        .read_text(encoding="utf-8")
    )


class EvidenceAgent:
    def __init__(self, spec: AgentSpec, llm, template: str | None = None):
        """``llm`` needs one method: with_structured_output(schema) -> runnable
        whose .invoke(prompt) returns an EvidenceDraft. Any LangChain chat
        model qualifies; tests pass fakes."""
        self.spec = spec
        self._template = template or load_team_template(spec.team.value)
        try:
            self._structured = llm.with_structured_output(EvidenceDraft)
        except Exception:
            logger.warning("%s: llm lacks structured output; agent will abstain",
                           spec.agent_id)
            self._structured = None

    def build_prompt(self, snapshot: MarketSnapshot,
                     extra_metrics: dict[str, MetricReading] | None = None,
                     ctx=None) -> str | None:
        # ``ctx`` lets analyze() reuse its already-rendered context — the
        # render is deterministic in (snapshot, spec, extra_metrics), and
        # rendering twice per agent per decision was a measured hot spot.
        if ctx is None:
            ctx = render_context(snapshot, self.spec, extra_metrics)
        if ctx.empty:
            return None
        missing_note = (
            "Unavailable inputs (do not guess at them): " + ", ".join(ctx.missing)
            if ctx.missing
            else "All requested inputs were available."
        )
        return self._template.format(
            persona=self.spec.persona,
            agent_id=self.spec.agent_id,
            asset=snapshot.asset.value,
            symbol=snapshot.symbol,
            timeframe=self.spec.timeframe.value,
            data_block=ctx.text,
            missing_note=missing_note,
        )

    def analyze(
        self,
        snapshot: MarketSnapshot,
        extra_metrics: dict[str, MetricReading] | None = None,
    ) -> AgentEvidence | None:
        """Produce evidence, or None (abstain) when data or parsing fails."""
        if self._structured is None:
            return None
        ctx = render_context(snapshot, self.spec, extra_metrics)
        if ctx.empty:
            logger.info("%s: no requested data available; abstaining", self.spec.agent_id)
            return None
        if self.spec.primary and not ctx.has_any(self.spec.primary):
            logger.info("%s: primary inputs %s unavailable; abstaining",
                        self.spec.agent_id, self.spec.primary)
            return None
        prompt = self.build_prompt(snapshot, extra_metrics, ctx=ctx)
        try:
            draft = self._structured.invoke(prompt)
        except Exception:
            logger.warning("%s: structured output failed; abstaining",
                           self.spec.agent_id, exc_info=True)
            return None
        if draft is None:
            return None
        return AgentEvidence(
            agent_id=self.spec.agent_id,
            team=self.spec.team,
            claim=draft.claim,
            direction=Direction(draft.direction),
            confidence=draft.confidence,
            timeframe=self.spec.timeframe,
            data_refs=ctx.data_refs,
            sources=list(ctx.sources.values()),
        )


def build_team(specs: Sequence[AgentSpec], llm) -> list[EvidenceAgent]:
    """Instantiate agents for a list of specs, loading each team template once."""
    templates: dict[str, str] = {}
    agents = []
    for spec in specs:
        key = spec.team.value
        if key not in templates:
            templates[key] = load_team_template(key)
        agents.append(EvidenceAgent(spec, llm, template=templates[key]))
    return agents


def run_agents(
    agents: Sequence[EvidenceAgent],
    snapshot: MarketSnapshot,
    extra_metrics: dict[str, MetricReading] | None = None,
) -> list[AgentEvidence]:
    """Run agents sequentially, collecting evidence; abstentions drop out.

    Parallel execution arrives with the Phase 6 graph work; this helper is
    the reference semantics.
    """
    evidence = []
    for agent in agents:
        result = agent.analyze(snapshot, extra_metrics)
        if result is not None:
            evidence.append(result)
    return evidence
