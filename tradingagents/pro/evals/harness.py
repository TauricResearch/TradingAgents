"""Decision-eval harness (review finding EVAL-01).

Runs the full pipeline over golden cases and scores structural and
directional properties that need no human label:

- schema success: every stage produced parseable structured output
- direction correctness: the judge did not take the forbidden action
- citation validity: every agent id cited in debate exists in the
  evidence record (fabricated citations = failure)
- injection resistance: poisoned cases must not flip the decision

With a fake LLM this validates harness mechanics only; the meaningful
run needs a real model:

    ~/.venvs/tradingagents-pro/bin/python -m tradingagents.pro.evals

CI gates on the structural run always, and on the model run when an API
key is configured.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tradingagents.contracts import ProConfig
from tradingagents.pro.evals.golden import GoldenCase, golden_cases
from tradingagents.pro.pipeline import run_pipeline


@dataclass
class CaseResult:
    name: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    action: str | None = None
    rejected_at: str | None = None


@dataclass
class EvalReport:
    results: list[CaseResult]

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def pass_rate(self) -> float:
        return sum(r.passed for r in self.results) / len(self.results)

    def summary(self) -> str:
        lines = [f"eval pass rate: {self.pass_rate:.0%} ({len(self.results)} cases)"]
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            detail = f" [{'; '.join(r.failures)}]" if r.failures else ""
            lines.append(f"  {status} {r.name}: action={r.action} "
                         f"rejected_at={r.rejected_at}{detail}")
        return "\n".join(lines)


def _evidence_agent_ids(state: dict) -> set[str]:
    return {
        e.agent_id
        for team in state.get("evidence_by_team", {}).values()
        for e in team
    }


def evaluate_case(llm, config: ProConfig, case: GoldenCase, **kwargs) -> CaseResult:
    state = run_pipeline(llm, config, case.snapshot, **kwargs)
    failures: list[str] = []

    rec = state.get("recommendation")
    rejection = state.get("rejection")
    action = rec.action.value if rec else None

    # structural: a golden case should produce either a recommendation or a
    # reasoned rejection — a crash or empty state is a harness failure
    if rec is None and rejection is None:
        failures.append("no recommendation and no rejection")

    # direction: taking the forbidden action on an unambiguous fixture fails
    if rec is not None and rec.action is case.forbidden_action:
        failures.append(
            f"took forbidden action {case.forbidden_action.value} ({case.notes})"
        )

    # citation validity: debate turns may only cite real evidence agents
    valid_ids = _evidence_agent_ids(state)
    for entry in state.get("debate", []):
        fabricated = [c for c in entry.get("cited", []) if c not in valid_ids]
        if fabricated:
            failures.append(f"{entry['speaker']} cited nonexistent agents {fabricated}")

    return CaseResult(
        name=case.name,
        passed=not failures,
        failures=failures,
        action=action,
        rejected_at=rejection and rejection.get("stage"),
    )


def run_decision_evals(llm, config: ProConfig | None = None,
                       cases: list[GoldenCase] | None = None, **kwargs) -> EvalReport:
    from tradingagents.contracts import AssetClass

    config = config or ProConfig(asset=AssetClass.GOLD, max_debate_rounds=1)
    cases = cases if cases is not None else golden_cases()
    return EvalReport([evaluate_case(llm, config, case, **kwargs) for case in cases])
