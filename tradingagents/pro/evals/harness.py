"""Decision-eval harness (EVAL-01), N-sample edition.

Per sample, scores properties needing no human label:
- structural: a recommendation or a reasoned rejection exists
- direction: no forbidden action taken on unambiguous fixtures
- overconfidence: on ambiguous fixtures, directional conviction above the
  case's cap is a failure
- citation validity: debate turns may only cite evidence that exists

Because identical inputs produce different outcomes run to run (observed
in the first live runs), ``samples > 1`` runs each case repeatedly and
reports per-case pass rates, outcome consistency, and a Wilson 95%
interval on the overall pass rate. A case *passes* only if every sample
passes — variance is a finding, not noise to average away.

Real-model entry point: ``python -m tradingagents.pro.evals``.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from tradingagents.contracts import ProConfig, TradeAction
from tradingagents.pro.evals.golden import GoldenCase, golden_cases
from tradingagents.pro.pipeline import run_pipeline


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


@dataclass
class CaseResult:
    name: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    action: str | None = None
    confidence: int | None = None
    rejected_at: str | None = None
    rejection_reasons: list[str] = field(default_factory=list)

    @property
    def outcome(self) -> str:
        return self.action or f"rejected:{self.rejected_at}"


@dataclass
class SampledCase:
    case: GoldenCase
    runs: list[CaseResult]

    @property
    def name(self) -> str:
        return self.case.name

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.runs)

    @property
    def pass_rate(self) -> float:
        return sum(r.passed for r in self.runs) / len(self.runs)

    @property
    def outcome_counts(self) -> Counter:
        return Counter(r.outcome for r in self.runs)

    @property
    def consistency(self) -> float:
        """Fraction of samples agreeing with the modal outcome."""
        return self.outcome_counts.most_common(1)[0][1] / len(self.runs)


@dataclass
class EvalReport:
    sampled: list[SampledCase]

    @property
    def results(self) -> list[CaseResult]:
        """All sample runs, flattened (one per case when samples=1)."""
        return [r for s in self.sampled for r in s.runs]

    @property
    def passed(self) -> bool:
        return all(s.passed for s in self.sampled)

    @property
    def pass_rate(self) -> float:
        runs = self.results
        return sum(r.passed for r in runs) / len(runs)

    def summary(self) -> str:
        runs = self.results
        n = len(runs)
        low, high = wilson_interval(sum(r.passed for r in runs), n)
        samples = len(self.sampled[0].runs) if self.sampled else 0
        lines = [
            f"eval pass rate: {self.pass_rate:.0%} over {n} runs "
            f"({len(self.sampled)} cases x {samples} samples); "
            f"95% CI [{low:.0%}, {high:.0%}]"
        ]
        for s in self.sampled:
            status = "PASS" if s.passed else "FAIL"
            outcomes = ", ".join(f"{o}x{c}" for o, c in s.outcome_counts.most_common())
            lines.append(
                f"  {status} {s.name}: {s.pass_rate:.0%} pass, "
                f"consistency {s.consistency:.0%} [{outcomes}]"
            )
            seen: set[str] = set()
            for r in s.runs:
                for failure in r.failures:
                    if failure not in seen:
                        seen.add(failure)
                        lines.append(f"       failure: {failure}")
                for reason in r.rejection_reasons:
                    if reason not in seen:
                        seen.add(reason)
                        lines.append(f"       reason: {reason}")
        injection = [s for s in self.sampled if "injection" in s.case.tags]
        if injection:
            inj_runs = [r for s in injection for r in s.runs]
            lines.append(
                f"injection subset: {sum(r.passed for r in inj_runs)}/{len(inj_runs)} "
                "runs resisted"
            )
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
    confidence = rec.confidence if rec else None

    if rec is None and rejection is None:
        failures.append("no recommendation and no rejection")

    if rec is not None and rec.action in case.forbidden_actions:
        failures.append(
            f"took forbidden action {rec.action.value} ({case.notes})"
        )

    if (
        rec is not None
        and case.max_directional_confidence is not None
        and rec.action is not TradeAction.HOLD
        and rec.confidence > case.max_directional_confidence
    ):
        failures.append(
            f"overconfident {rec.action.value}@{rec.confidence} on ambiguous "
            f"fixture (cap {case.max_directional_confidence}: {case.notes})"
        )

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
        confidence=confidence,
        rejected_at=rejection and rejection.get("stage"),
        rejection_reasons=list(rejection.get("reasons", [])) if rejection else [],
    )


def run_decision_evals(
    llm,
    config: ProConfig | None = None,
    cases: list[GoldenCase] | None = None,
    samples: int = 1,
    tag: str | None = None,
    **kwargs,
) -> EvalReport:
    from tradingagents.contracts import AssetClass

    if samples < 1:
        raise ValueError("samples must be >= 1")
    config = config or ProConfig(asset=AssetClass.GOLD, max_debate_rounds=1)
    cases = cases if cases is not None else golden_cases()
    if tag is not None:
        cases = [c for c in cases if tag in c.tags]
        if not cases:
            raise ValueError(f"no golden cases tagged {tag!r}")
    return EvalReport([
        SampledCase(case=case, runs=[
            evaluate_case(llm, config, case, **kwargs) for _ in range(samples)
        ])
        for case in cases
    ])
