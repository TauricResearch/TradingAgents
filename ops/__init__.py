"""Operational live-trading layer on top of TradingAgents.

The recommended way to build a guarded paper broker is the
`build_guarded_paper_broker` factory below — it assembles the inner
PaperBroker, the canonical rule chain, and the GuardedBroker wrapper
in one place and never exposes the inner broker to callers.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable

from ops.broker.guarded import GuardedBroker
from ops.broker.paper import PaperBroker
from ops.config import OpsConfig
from ops.guardrails.drawdown_rules import DailyDrawdownRule, WeeklyDrawdownRule
from ops.guardrails.engine import RuleEngine
from ops.guardrails.sizing_rules import (
    CashReserveRule,
    MaxOpenPositionsRule,
    PerPositionCapRule,
    PerTradeDollarFloorRule,
)
from ops.guardrails.static_rules import (
    DenyListRule,
    FractionalSharesOnlyRule,
    LongOnlyRule,
    NoCryptoRule,
    NoMarginRule,
    NoOptionsRule,
    StopAttachedRule,
)
from ops.journal import Journal

EquityFn = Callable[[], Decimal]


def build_default_rule_chain(
    *,
    start_of_day_equity: EquityFn,
    start_of_week_equity: EquityFn,
) -> list:
    """Canonical rule order for v1.

    Static/symbol checks first (cheapest, no broker state),
    then order-shape, sizing, and finally account-state rules.
    This ordering only affects WHICH rule name is reported when multiple
    would fail; it does not change whether an order is allowed.
    """
    return [
        DenyListRule(),
        NoMarginRule(),
        NoOptionsRule(),
        NoCryptoRule(),
        LongOnlyRule(),
        StopAttachedRule(),
        FractionalSharesOnlyRule(),
        PerTradeDollarFloorRule(),
        PerPositionCapRule(),
        MaxOpenPositionsRule(),
        CashReserveRule(),
        DailyDrawdownRule(start_of_day_equity=start_of_day_equity),
        WeeklyDrawdownRule(start_of_week_equity=start_of_week_equity),
    ]


def build_guarded_paper_broker(
    *,
    config: OpsConfig,
    journal: Journal,
    quote_source: Callable[[str], Decimal],
    starting_cash: Decimal,
    start_of_day_equity: EquityFn,
    start_of_week_equity: EquityFn,
) -> GuardedBroker:
    """Build a guarded paper broker. The inner PaperBroker is constructed
    here and never returned, so callers cannot bypass the rule chain by
    holding a reference to the unwrapped broker."""
    inner = PaperBroker(
        journal=journal,
        quote_source=quote_source,
        starting_cash=starting_cash,
    )
    engine = RuleEngine(
        build_default_rule_chain(
            start_of_day_equity=start_of_day_equity,
            start_of_week_equity=start_of_week_equity,
        )
    )
    return GuardedBroker(inner=inner, engine=engine, journal=journal, config=config)


__all__ = [
    "OpsConfig",
    "Journal",
    "GuardedBroker",
    "build_default_rule_chain",
    "build_guarded_paper_broker",
]
