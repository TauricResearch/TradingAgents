"""Scripted structured-output LLM — deterministic, zero-cost.

Lives in the package (not tests/) because the dashboard's replay endpoint
uses it in production for the "mechanics simulation" backtest: the REAL
pipeline over REAL bars with canned model output, exercising gates,
sizing, fills and exits — clearly labeled as plumbing, never model skill.
Tests import it from here.
"""

from __future__ import annotations

from tradingagents.pro.agents import EvidenceDraft
from tradingagents.pro.pipeline import (
    CriticReport,
    DebateTurn,
    JudgeVerdict,
    ReflectionNote,
)
from tradingagents.pro.pipeline.qa import EvidenceAnswer

DEFAULT_DRAFTS = {
    EvidenceAnswer: EvidenceAnswer(
        answerable=True,
        answer="Per the cited evidence, the prevailing side carried the debate.",
        cited_agent_ids=["rsi"],
    ),
    EvidenceDraft: EvidenceDraft(
        claim="Signal favors upside per the shown values.",
        direction="bullish",
        confidence=60,
    ),
    DebateTurn: DebateTurn(
        argument="The cited momentum evidence carries the case.",
        cited_agent_ids=["rsi"],
        confidence=55,
    ),
    CriticReport: CriticReport(verdict="pass", issues=[]),
    ReflectionNote: ReflectionNote(
        weaknesses="Momentum evidence is single-timeframe.",
        invalidation="A close below the shown stop level.",
    ),
    JudgeVerdict: JudgeVerdict(
        action="BUY", confidence=72,
        rationale="Bull side carried the debate; risk numbers within limits.",
    ),
}


class FakeRunnable:
    def __init__(self, payload, log):
        self.payload = payload
        self.log = log

    def invoke(self, prompt):
        self.log.append(prompt)
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakePipelineLLM:
    """Serves canned structured outputs per schema; records every prompt."""

    def __init__(self, overrides: dict | None = None):
        self.overrides = overrides or {}
        self.prompts: dict[str, list[str]] = {}

    def with_structured_output(self, schema):
        payload = self.overrides.get(schema, DEFAULT_DRAFTS[schema])
        return FakeRunnable(payload, self.prompts.setdefault(schema.__name__, []))
