"""Point-in-time replay harness for TradingAgents.

The framework's data layer is deliberately point-in-time: FRED pins its vintage
to the as-of date (#1275), social and news are trimmed to the analysis window
(#1220), indicators are cut at ``curr_date``, and the decision log only replays
lessons whose outcome was already known (#1251). This package is the consumer
of that work — it replays the agent graph over a date range and scores the
resulting decisions as a portfolio.

The design separates two things that have very different costs:

* **Producing decisions** is slow and expensive (one full agent graph run per
  decision point). :mod:`~tradingagents.backtest.runner` does that once and
  appends every decision to a JSONL store.
* **Scoring decisions** is free. :mod:`~tradingagents.backtest.portfolio` and
  :mod:`~tradingagents.backtest.metrics` read the store, so re-scoring under a
  different weight map, cost model, or metric costs no LLM calls at all.

Nothing in this package calls an LLM or the network directly: the runner takes
an injected graph factory and the portfolio takes an injected price frame, so
the whole harness is testable offline.
"""

from tradingagents.backtest.portfolio import (
    DEFAULT_WEIGHTS,
    PortfolioConfig,
    simulate,
)
from tradingagents.backtest.schedule import decision_dates
from tradingagents.backtest.store import (
    SCHEMA_VERSION,
    DecisionRecord,
    DecisionStore,
)

__all__ = [
    "DEFAULT_WEIGHTS",
    "SCHEMA_VERSION",
    "DecisionRecord",
    "DecisionStore",
    "PortfolioConfig",
    "decision_dates",
    "simulate",
]
