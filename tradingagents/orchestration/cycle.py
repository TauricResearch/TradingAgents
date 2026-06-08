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
    PortfolioProposal,
    admit_within_statute,
    assess_costs,
    build_trade,
    can_trade,
    inject_portfolio_state,
    manage_exits,
    persist_trade,
    run_mantainer,
    submit_trade,
)
from ..storage import repository as repo
from ..storage.models import Trade
from .analyze import Analyzer
from .triggers import TriggerEvent, collect_triggers

# Trigger types that, on a non-watchlist universe ticker, get it onto the
# watchlist (the dynamic entry Luca described: a news/alert on a new name).
_WATCHLIST_ADMIT_TYPES = {"price_alert", "news", "watchlist_candidate"}


@dataclass
class CycleReport:
    triggers: int = 0
    analyzed: int = 0
    traded: int = 0
    closed: int = 0
    skipped_not_tradable: int = 0
    skipped_cost: int = 0
    skipped_portfolio: int = 0
    watchlist_added: int = 0
    trades: list[Trade] = field(default_factory=list)
    closed_trades: list[Trade] = field(default_factory=list)
    events: list[TriggerEvent] = field(default_factory=list)


def _admit_watchlist(session: Session, events: list[TriggerEvent]) -> int:
    """Dynamic entry: a news/alert on a non-watchlist universe ticker joins it."""
    universe = repo.universe_symbols(session)
    watch = repo.watchlist_symbols(session)
    added = 0
    for ev in events:
        if (ev.type in _WATCHLIST_ADMIT_TYPES and ev.symbol in universe
                and ev.symbol not in watch):
            repo.set_watchlist(session, ev.symbol, True, reason=ev.type)
            watch.add(ev.symbol)
            added += 1
    return added


def run_cycle(
    session: Session,
    broker: Broker,
    analyze: Analyzer,
    *,
    batch_analyze: Optional[Any] = None,   # Director: symbols -> {symbol: state}
    commission_model: Optional[CommissionModel] = None,
    token_cost: float = 0.0,
    top_k: int = 5,
    today: Optional[date] = None,
    charter: Optional[dict[str, Any]] = None,
    **sizing: Any,
) -> CycleReport:
    """Run one orchestration cycle and return a report.

    Three stages: (1) manage exits; (2) the Director analyses the triggered
    working set (in parallel via ``batch_analyze`` if given, else one by one);
    (3) the portfolio-level Statute admits buys that keep the whole book legal,
    then execution (serial). Per-ticker risk already happened in each Evaluator.
    """
    report = CycleReport()
    report.closed_trades = manage_exits(session, broker)
    report.closed = len(report.closed_trades)

    events = collect_triggers(session, top_k=top_k, today=today)
    report.triggers = len(events)
    report.events = events
    report.watchlist_added = _admit_watchlist(session, events)

    symbols: list[str] = []
    for ev in events:
        if ev.symbol not in symbols:
            symbols.append(ev.symbol)

    portfolio = inject_portfolio_state(session)
    portfolio_value = portfolio.get("total_value", 0.0)

    # --- analyse (Evaluators) -------------------------------------------
    if batch_analyze is not None:
        states = batch_analyze(symbols)
    else:
        states = {}
        for sym in symbols:
            st = analyze(session, sym)
            if st is not None:
                states[sym] = st

    # --- first pass: persist cards, build tradable proposals ------------
    proposals: list[dict[str, Any]] = []  # {symbol,state,order,commission}
    for sym in symbols:
        state = states.get(sym)
        if state is None:
            continue
        report.analyzed += 1
        repo.upsert_ticker_card(
            session, sym,
            latest_direction=state.direction.value if state.direction else None,
            latest_conviction=state.conviction_level.value if state.conviction_level else None,
            next_check_date=state.next_check_date,
            latest_summary={
                "pro": state.pro, "contro": state.contro,
                "risk_verdict": state.risk.verdict.value if state.risk.verdict else None,
            },
        )
        if not can_trade(state):
            report.skipped_not_tradable += 1
            _log(session, sym, state, traded=False)
            continue
        order = build_trade(state, portfolio_value, **sizing)
        commission = (
            commission_model.estimate(order.symbol, order.quantity, order.entry_price)
            if commission_model else 0.0
        )
        assert state.levels is not None
        if not assess_costs(state.levels, order.quantity,
                            commission=commission, token_cost=token_cost).ok:
            report.skipped_cost += 1
            _log(session, sym, state, traded=False)
            continue
        proposals.append({"symbol": sym, "state": state, "order": order, "commission": commission})

    # --- portfolio-level Statute (the Director's aggregate gate) ---------
    pp = [
        PortfolioProposal(
            symbol=p["symbol"],
            position_value=p["order"].sizing.position_value,
            risk_value=p["order"].sizing.euro_at_risk,
            sector=repo.instrument_sector(session, p["symbol"]),
        )
        for p in proposals
    ]
    admitted = set(admit_within_statute(session, pp, charter=charter).admitted)

    # --- execute admitted (serial, safe for broker/DB) ------------------
    for p in proposals:
        sym, state, order, commission = p["symbol"], p["state"], p["order"], p["commission"]
        if sym not in admitted:
            report.skipped_portfolio += 1
            _log(session, sym, state, traded=False)
            continue
        trade = persist_trade(session, order, payload=state.seal())
        trade.commission = commission
        trade.token_cost = token_cost
        submit_trade(session, trade, broker)
        report.trades.append(trade)
        _log(session, sym, state, traded=True, client_order_id=trade.client_order_id)

    report.traded = len(report.trades)
    run_mantainer(session, broker)
    return report


def _log(session, symbol, state, *, traded, client_order_id=None) -> None:
    """Learning-loop substrate: thesis + per-agent opinions + outcome."""
    repo.log_decision(
        session,
        symbol=symbol,
        direction=state.direction.value if state.direction else None,
        conviction=state.conviction_level.value if state.conviction_level else None,
        risk_verdict=state.risk.verdict.value if state.risk.verdict else None,
        agent_opinions=[o.model_dump(mode="json") for o in state.agent_opinions],
        payload=state.seal(),
        traded=traded,
        client_order_id=client_order_id,
    )
