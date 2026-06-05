"""The cycle runner: one pass of the autonomous loop.

    triggers -> analyze (graph) -> cost gate -> execute

Deterministic everywhere except ``analyze`` (the LLM graph). Returns a report so
a caller/scheduler can log why the cycle did what it did.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..broker.base import Broker
from ..broker.commission import CommissionModel
from ..execution import (
    assess_costs,
    build_trade,
    can_trade,
    inject_portfolio_state,
    persist_trade,
    submit_trade,
)
from ..storage.models import Trade
from .analyze import Analyzer
from .triggers import TriggerEvent, collect_triggers


@dataclass
class CycleReport:
    triggers: int = 0
    analyzed: int = 0
    traded: int = 0
    skipped_not_tradable: int = 0
    skipped_cost: int = 0
    trades: list[Trade] = field(default_factory=list)
    events: list[TriggerEvent] = field(default_factory=list)


def run_cycle(
    session: Session,
    broker: Broker,
    analyze: Analyzer,
    *,
    commission_model: Optional[CommissionModel] = None,
    token_cost: float = 0.0,
    top_k: int = 5,
    today: Optional[date] = None,
    **sizing: Any,
) -> CycleReport:
    """Run one orchestration cycle and return a report."""
    events = collect_triggers(session, top_k=top_k, today=today)
    report = CycleReport(triggers=len(events), events=events)

    portfolio = inject_portfolio_state(session)
    portfolio_value = portfolio.get("total_value", 0.0)

    for ev in events:
        state = analyze(session, ev.symbol)
        if state is None:
            continue
        report.analyzed += 1

        if not can_trade(state):
            report.skipped_not_tradable += 1
            continue

        proposal = build_trade(state, portfolio_value, **sizing)

        # Cost gate: the potential reward must cover broker + token costs.
        commission = (
            commission_model.estimate(proposal.symbol, proposal.quantity, proposal.entry_price)
            if commission_model
            else 0.0
        )
        assert state.levels is not None
        assessment = assess_costs(
            state.levels, proposal.quantity, commission=commission, token_cost=token_cost
        )
        if not assessment.ok:
            report.skipped_cost += 1
            continue

        # Execute: persist (with sealed thesis) then submit to the broker.
        trade = persist_trade(session, proposal, payload=state.seal())
        submit_trade(session, trade, broker)
        report.trades.append(trade)

    report.traded = len(report.trades)
    return report
