"""Rules engine: deterministic indicator-driven pipeline "model".

Drop-in for the LLM in the pipeline's structured-output seam, but honest
about what it is: evidence agents vote via a-priori technical rules on the
exact values their spec shows them (``analytics/signals.py``); the judge
becomes the confidence-weighted consensus with an ADX chop filter; debate/
critic/reflection are deterministic pass-throughs. Zero cost, zero
network, same geometry/gates/sizing code as the real-LLM path.

Replaces the canned always-BUY ``FakePipelineLLM`` for the dashboard's
deterministic backtests (that one remains for tests that need scripted
plumbing). Evidence-driven change: a 5m BTC audit showed the canned BUY
produced 2,015/2,015 BUY proposals — entries with no entry logic.
"""

from __future__ import annotations

from tradingagents.pro.agents import EvidenceDraft
from tradingagents.pro.analytics.signals import evaluate_refs
from tradingagents.pro.evals.scripted import DEFAULT_DRAFTS, FakeRunnable
from tradingagents.pro.pipeline import (
    CriticReport,
    DebateTurn,
    JudgeVerdict,
    ReflectionNote,
)
from tradingagents.pro.pipeline.qa import EvidenceAnswer

_RULES_DRAFTS = {
    EvidenceAnswer: EvidenceAnswer(
        answerable=True,
        answer="Deterministic rules mode: the verdict is the confidence-"
               "weighted consensus of indicator-rule votes.",
        cited_agent_ids=["rsi"],
    ),
    DebateTurn: DebateTurn(
        argument="Deterministic rules mode: positions follow the recorded "
                 "indicator votes; no rhetorical rebuttal is generated.",
        cited_agent_ids=["rsi"],
        confidence=50,
    ),
    CriticReport: CriticReport(verdict="pass", issues=[]),
    ReflectionNote: ReflectionNote(
        weaknesses="Rule votes read single-snapshot indicator state; no "
                   "regime memory beyond the shown window.",
        invalidation="A close beyond the engine stop level invalidates "
                     "the thesis.",
    ),
    # judge fallback only — the pipeline's rules-mode branch bypasses the
    # judge model entirely and uses the deterministic consensus
    JudgeVerdict: JudgeVerdict(
        action="HOLD", confidence=0,
        rationale="rules mode: judge is the deterministic consensus",
    ),
}


class RulesEvidenceRunnable:
    """Evidence 'model': votes via signal rules on the agent's own refs."""

    def __init__(self, log: list):
        self.log = log

    def invoke(self, prompt: str):
        # no refs available on this call path — abstain rather than fake
        self.log.append(prompt)
        return None

    def invoke_with_refs(self, prompt: str, spec, data_refs):
        self.log.append(prompt)
        refs = {r.name: r.value for r in data_refs
                if isinstance(r.value, (int, float))}
        result = evaluate_refs(refs)
        if result is None:
            return None  # agent abstains: no numeric rule applies
        direction, confidence, claim = result
        return EvidenceDraft(claim=claim, direction=direction,
                             confidence=confidence)


class RulesPipelineLLM:
    """Serves rule-driven evidence + deterministic pass-throughs."""

    is_rules_engine = True

    def __init__(self):
        self.prompts: dict[str, list[str]] = {}

    def with_structured_output(self, schema):
        log = self.prompts.setdefault(schema.__name__, [])
        if schema is EvidenceDraft:
            return RulesEvidenceRunnable(log)
        payload = _RULES_DRAFTS.get(schema, DEFAULT_DRAFTS.get(schema))
        return FakeRunnable(payload, log)
