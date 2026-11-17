"""Member C offline verification fixtures.

Synthetic inputs only: no network, no provider calls, no real holdings.
A scripted engine stands in for the graph so the shared run boundary can be
exercised deterministically. Application code is not modified.
"""

from __future__ import annotations

import pytest

from tradingagents.portfolio import PortfolioContext
from tradingagents.runapi.context import ConsentState
from tradingagents.runapi.input_service import freeze_explicit


def make_engine(final_state: dict, *, raises: BaseException | None = None):
    """A graph_factory replacement returning an object usable by run_analysis_api.

    run_analysis_api calls factory(...) then passes the object to engine_runner.
    Our engine_runner ignores args and returns the scripted state (or raises).
    """

    class _Engine:
        def __init__(self):
            self.calls = 0

    def factory(*_args, **_kwargs):
        return _Engine()

    def runner(_graph, _context):
        _graph.calls += 1
        if raises is not None:
            raise raises
        return final_state

    return factory, runner


def confirmed_context(ticker="AAPL", analysis_date="2026-11-12", portfolio=None):
    ctx = freeze_explicit(ticker, analysis_date, portfolio)
    assert ctx.consent_state == ConsentState.FROZEN
    return ctx.confirm()


GOOD_STATE = {
    "market_report": "MKT",
    "news_report": "NEWS",
    "investment_debate_state": {"bull_history": "BULL", "bear_history": "BEAR"},
    "investment_plan": "RESEARCH PLAN",
    "trader_investment_plan": "TRADE PLAN",
    "risk_debate_state": {"neutral_history": "NEUTRAL"},
    "final_trade_decision": "Rating: Hold\n\nBalanced view.",
    "final_rating": "Hold",
}


@pytest.fixture
def holding_portfolio():
    return PortfolioContext.model_validate({
        "cash": 25000.0,
        "currency": "USD",
        "positions": [
            {"ticker": "AAPL", "quantity": 120, "average_price": 150.0},
            {"ticker": "MSFT", "quantity": 10},
        ],
    })
