"""Hard, reviewable gate for thesis/action contradictions in evaluation data."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DecisionDirection = Literal["buy", "sell", "hold", "abstain"]
ThesisDirection = Literal["bullish", "bearish", "neutral", "abstain"]


@dataclass(frozen=True)
class DecisionEvaluationCase:
    case_id: str
    thesis: ThesisDirection
    action: DecisionDirection
    risk_disclosed: bool
    target_model: str
    judge_model: str

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id is required")
        if self.target_model.strip() and self.target_model == self.judge_model:
            raise ValueError("judge_model must differ from target_model")


@dataclass(frozen=True)
class ContradictionResult:
    contradictory: bool
    reasons: tuple[str, ...]
    score: float


def evaluate_contradictions(case: DecisionEvaluationCase) -> ContradictionResult:
    """Return score 0 for an action that contradicts its directional thesis."""
    reasons: list[str] = []
    if case.thesis == "bullish" and case.action == "sell":
        reasons.append("bullish_thesis_with_sell_action")
    elif case.thesis == "bearish" and case.action == "buy":
        reasons.append("bearish_thesis_with_buy_action")
    elif case.thesis == "abstain" and case.action not in {"hold", "abstain"}:
        reasons.append("abstain_thesis_with_directional_action")
    if reasons:
        return ContradictionResult(True, tuple(reasons), 0.0)
    return ContradictionResult(False, (), 1.0 if case.risk_disclosed else 0.75)


def require_no_contradiction(case: DecisionEvaluationCase) -> ContradictionResult:
    result = evaluate_contradictions(case)
    if result.contradictory:
        raise ValueError("contradiction gate failed: " + ", ".join(result.reasons))
    return result


def load_eval_cases(path: str | Path) -> list[DecisionEvaluationCase]:
    """Load reviewable CSV fixtures without invoking a judge model."""
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        return [
            DecisionEvaluationCase(
                case_id=str(row["case_id"]),
                thesis=str(row["thesis"]),  # type: ignore[arg-type]
                action=str(row["action"]),  # type: ignore[arg-type]
                risk_disclosed=str(row.get("risk_disclosed", "")).casefold() == "true",
                target_model=str(row.get("target_model", "")),
                judge_model=str(row.get("judge_model", "")),
            )
            for row in rows
        ]
