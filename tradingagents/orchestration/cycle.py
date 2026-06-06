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
    manage_exits,
    persist_trade,
    submit_trade,
)
from ..storage import repository as repo
from ..storage.models import Trade
from .analyze import Analyzer
from .triggers import TriggerEvent, collect_triggers


@dataclass
class CycleReport:
    triggers: int = 0
    analyzed: int = 0
    traded: int = 0
    closed: int = 0
    skipped_not_tradable: int = 0
    skipped_cost: int = 0
    trades: list[Trade] = field(default_factory=list)
    closed_trades: list[Trade] = field(default_factory=list)
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
    # First manage what we already hold (stop-loss / take-profit exits).
    report = CycleReport()
    report.closed_trades = manage_exits(session, broker)
    report.closed = len(report.closed_trades)

    events = collect_triggers(session, top_k=top_k, today=today)
    report.triggers = len(events)
    report.events = events

    portfolio = inject_portfolio_state(session)
    portfolio_value = portfolio.get("total_value", 0.0)

    for ev in events:
        state = analyze(session, ev.symbol)
        if state is None:
            continue
        report.analyzed += 1

        # The deep-dive updates the persistent ticker card (B/C): latest call +
        # the Dynamic Temporal Checkpoint, so the trigger engine can re-wake it.
        repo.upsert_ticker_card(
            session, ev.symbol,
            latest_direction=state.direction.value if state.direction else None,
            latest_conviction=state.conviction_level.value if state.conviction_level else None,
            next_check_date=state.next_check_date,
            latest_summary={
                "pro": state.pro, "contro": state.contro,
                "risk_verdict": state.risk.verdict.value if state.risk.verdict else None,
            },
        )

        traded = False
        client_order_id = None

        if not can_trade(state):
            report.skipped_not_tradable += 1
        else:
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
            else:
                # Execute: persist (with sealed thesis) then submit to the broker.
                trade = persist_trade(session, proposal, payload=state.seal())
                trade.commission = commission
                trade.token_cost = token_cost
                submit_trade(session, trade, broker)
                report.trades.append(trade)
                traded = True
                client_order_id = trade.client_order_id

        # Learning-loop substrate: log the thesis + per-agent opinions + outcome.
        repo.log_decision(
            session,
            symbol=ev.symbol,
            direction=state.direction.value if state.direction else None,
            conviction=state.conviction_level.value if state.conviction_level else None,
            risk_verdict=state.risk.verdict.value if state.risk.verdict else None,
            agent_opinions=[o.model_dump(mode="json") for o in state.agent_opinions],
            payload=state.seal(),
            traded=traded,
            client_order_id=client_order_id,
        )

    report.traded = len(report.trades)
    return report
