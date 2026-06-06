"""Structured F4 alert strictness evaluator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List, Literal

from pydantic import BaseModel, Field, ValidationError


class AlertEvaluationPayload(BaseModel):
    decision: Literal["pass", "reject"]
    score: float = Field(ge=0.0, le=1.0)
    materiality: str
    actionability: str
    ticker_link_evidence: str
    novelty: str
    disqualifiers: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)


@dataclass(frozen=True)
class AlertEvaluation:
    passed: bool
    score: float
    payload: dict
    disqualifiers: list[str]


def build_alert_evaluation_prompt(*, event_text: str, tickers: list[str]) -> str:
    return (
        "You are the IIC-FORGE alert quality gate. Decide whether this event "
        "is worth sending a light alert to a human investor before any full study. "
        "Reject stale, duplicated, vague, weakly ticker-linked, low-materiality, "
        "or non-actionable events. Pass only when the event has a direct ticker "
        "link and could plausibly change a watchlist thesis or near-term decision.\n\n"
        "Return strict JSON with keys: decision, score, materiality, actionability, "
        "ticker_link_evidence, novelty, disqualifiers, reasons.\n\n"
        f"TICKERS: {', '.join(tickers)}\n\n"
        f"EVENT:\n{event_text[:5000]}"
    )


def evaluate_alert_candidate(
    *,
    llm: Any,
    event_text: str,
    tickers: list[str],
    min_score: float,
) -> AlertEvaluation:
    prompt = build_alert_evaluation_prompt(event_text=event_text, tickers=tickers)
    try:
        resp = llm.invoke(prompt)
        raw = getattr(resp, "content", str(resp))
        payload = AlertEvaluationPayload.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return AlertEvaluation(
            passed=False,
            score=0.0,
            payload={"decision": "reject", "score": 0.0},
            disqualifiers=["invalid_json"],
        )

    passed = (
        payload.decision == "pass"
        and payload.score >= min_score
        and not payload.disqualifiers
    )
    return AlertEvaluation(
        passed=passed,
        score=payload.score,
        payload=payload.model_dump(),
        disqualifiers=list(payload.disqualifiers),
    )
