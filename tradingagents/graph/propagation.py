# TradingAgents/graph/propagation.py

from datetime import date, datetime
from typing import Any

from tradingagents.agents.utils.agent_states import (
    InvestDebateState,
    RiskDebateState,
)


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(
        self,
        max_recur_limit=100,
        *,
        selected_analysts: tuple[str, ...] | list[str] | None = None,
        research_safety_policy: dict[str, Any] | None = None,
        research_run_metadata: dict[str, Any] | None = None,
    ):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit
        self.selected_analysts = tuple(
            selected_analysts or ("market", "social", "news", "fundamentals")
        )
        self.research_safety_policy = research_safety_policy
        self.research_run_metadata = dict(research_run_metadata or {})

    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        asset_type: str = "stock",
        past_context: str = "",
        instrument_context: str = "",
    ) -> dict[str, Any]:
        """Create the initial state for the agent graph.

        ``instrument_context`` is the deterministic ticker-identity string
        resolved once at run start (see
        ``TradingAgentsGraph.resolve_instrument_context``). When empty, agents
        fall back to ticker-only context via
        ``get_instrument_context_from_state``.
        """
        analysis_date = datetime.strptime(str(trade_date), "%Y-%m-%d").date()
        if analysis_date > date.today():
            raise ValueError("trade_date cannot be in the future")
        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "asset_type": asset_type,
            "instrument_context": instrument_context,
            "trade_date": str(trade_date),
            "past_context": past_context,
            "research_safety_policy": self.research_safety_policy,
            "research_run_metadata": {
                **self.research_run_metadata,
                "selected_analysts": list(self.selected_analysts),
            },
            "research_result": {},
            "research_signal": {},
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
