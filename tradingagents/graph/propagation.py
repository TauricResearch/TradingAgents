# TradingAgents/graph/propagation.py

from typing import Dict, Any, List, Optional
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100, max_concurrency: Optional[int] = None):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit
        self.max_concurrency = max_concurrency

    def create_initial_state(
        self, company_name: str, trade_date: str, past_context: str = ""
    ) -> Dict[str, Any]:
        """Create the initial state for the agent graph."""
        start_msg = [("human", company_name)]
        return {
            "messages": start_msg,
            "company_of_interest": company_name,
            "trade_date": str(trade_date),
            "past_context": past_context,
            "market_messages": start_msg,
            "sentiment_messages": start_msg,
            "news_messages": start_msg,
            "fundamentals_messages": start_msg,
            "analyst_count": 0,
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

    def get_graph_args(self, callbacks: Optional[List] = None) -> Dict[str, Any]:
        """Get arguments for the graph invocation.

        Args:
            callbacks: Optional list of callback handlers for tool execution tracking.
                       Note: LLM callbacks are handled separately via LLM constructor.
        """
        config = {"recursion_limit": self.max_recur_limit}
        if self.max_concurrency is not None:
            config["max_concurrency"] = self.max_concurrency
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "updates",
            "config": config,
        }
