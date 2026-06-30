"""RuleEngine: evaluates an ordered sequence of guardrail rules.

Rules are checked in order; the first rejection short-circuits evaluation
and is returned immediately without invoking any subsequent rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ops.guardrails.base import Rule, RuleContext


@dataclass(frozen=True)
class EngineResult:
    allowed: bool
    reason: str = ""
    failed_rule_name: str = ""


class RuleEngine:
    def __init__(self, rules: Sequence[Rule]):
        self._rules = list(rules)

    def evaluate(self, ctx: RuleContext) -> EngineResult:
        for rule in self._rules:
            result = rule.check(ctx)
            if not result.allowed:
                return EngineResult(
                    allowed=False, reason=result.reason, failed_rule_name=rule.name
                )
        return EngineResult(allowed=True)
