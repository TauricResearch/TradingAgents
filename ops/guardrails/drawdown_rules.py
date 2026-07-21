# ops/guardrails/drawdown_rules.py
from __future__ import annotations

from decimal import Decimal
from typing import Callable

from ops.broker.types import Side
from ops.guardrails.base import Rule, RuleContext, RuleResult

EquityFn = Callable[[], Decimal]


class DailyDrawdownRule(Rule):
    """Blocks BUYs when today's loss vs. start-of-day equity is at or past
    the threshold. SELLs are always allowed."""

    def __init__(self, start_of_day_equity: EquityFn):
        self._start = start_of_day_equity

    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.side != Side.BUY:
            return RuleResult.allow()
        start = self._start()
        if start <= 0:
            return RuleResult.allow()
        current = ctx.broker.get_equity()
        pct = (current - start) / start
        if pct <= ctx.config.daily_drawdown_pct:
            return RuleResult.reject(
                f"daily drawdown {pct} at or below threshold "
                f"{ctx.config.daily_drawdown_pct}; new BUYs halted"
            )
        return RuleResult.allow()


class WeeklyDrawdownRule(Rule):
    """Blocks BUYs when this week's loss vs. start-of-week equity is at or
    past the threshold. SELLs are always allowed (kill-switch auto-close
    happens in the orchestrator, not in this rule)."""

    def __init__(self, start_of_week_equity: EquityFn):
        self._start = start_of_week_equity

    def check(self, ctx: RuleContext) -> RuleResult:
        if ctx.order.side != Side.BUY:
            return RuleResult.allow()
        start = self._start()
        if start <= 0:
            return RuleResult.allow()
        current = ctx.broker.get_equity()
        pct = (current - start) / start
        if pct <= ctx.config.weekly_drawdown_pct:
            return RuleResult.reject(
                f"weekly drawdown {pct} at or below threshold "
                f"{ctx.config.weekly_drawdown_pct}; new BUYs halted"
            )
        return RuleResult.allow()
