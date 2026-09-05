# TradingAgents/graph/propagation.py

from typing import Any

from tradingagents.agents.schemas import PortfolioContext
from tradingagents.agents.utils.agent_states import (
    InvestDebateState,
    RiskDebateState,
)


def normalize_portfolio_context(
    portfolio_context: PortfolioContext | dict | None,
) -> dict | None:
    """Normalize a caller-supplied portfolio context to JSON-safe state data.

    Accepts a ``PortfolioContext`` or its ``dict`` form; ``None`` is passed
    through and means the context was not provided. Validation failures raise
    ``pydantic.ValidationError`` so a malformed snapshot fails at run start
    rather than silently degrading into an empty portfolio.
    """
    if portfolio_context is None:
        return None
    if isinstance(portfolio_context, PortfolioContext):
        context = portfolio_context
    else:
        context = PortfolioContext.model_validate(portfolio_context)
    return context.model_dump(mode="json")


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        asset_type: str = "stock",
        past_context: str = "",
        instrument_context: str = "",
        portfolio_context: PortfolioContext | dict | None = None,
    ) -> dict[str, Any]:
        """Create the initial state for the agent graph.

        ``instrument_context`` is the deterministic ticker-identity string
        resolved once at run start (see
        ``TradingAgentsGraph.resolve_instrument_context``). When empty, agents
        fall back to ticker-only context via
        ``get_instrument_context_from_state``.

        ``portfolio_context`` is the optional broker-neutral portfolio
        snapshot (see ``PortfolioContext``). When omitted, the state records
        ``None`` so decision nodes can distinguish "not provided" from a
        known flat portfolio.
        """
        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "asset_type": asset_type,
            "instrument_context": instrument_context,
            "trade_date": str(trade_date),
            "past_context": past_context,
            "portfolio_context": normalize_portfolio_context(portfolio_context),
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "risk_debate_state": RiskDebateState(
                {
                    "aggressive_history": "",
                    "conservative_history": "",
                    "neutral_history": "",
                    "history": "",
                    "latest_speaker": "",
                    "current_aggressive_response": "",
                    "current_conservative_response": "",
                    "current_neutral_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "market_report": "",
            "fundamentals_report": "",
            "sentiment_report": "",
            "news_report": "",
        }

    def get_graph_args(self, callbacks: list | None = None) -> dict[str, Any]:
        """Get arguments for the graph invocation.

        Args:
            callbacks: Optional list of callback handlers for tool execution tracking.
                       Note: LLM callbacks are handled separately via LLM constructor.
        """
        config = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "values",
            "config": config,
        }
