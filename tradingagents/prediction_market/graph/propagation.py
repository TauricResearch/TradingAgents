# TradingAgents/prediction_market/graph/propagation.py

from typing import Dict, Any, List, Optional
from tradingagents.prediction_market.agents.utils.pm_agent_states import (
    PMAgentState,
    PMInvestDebateState,
    PMRiskDebateState,
)


class PMPropagator:
    """Handles state initialization and propagation through the prediction market graph."""

    def __init__(self, max_recur_limit=100):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self, market_id: str, trade_date: str, market_question: str = ""
    ) -> Dict[str, Any]:
        """Create the initial state for the prediction market agent graph."""
        return {
            "messages": [("human", market_question or market_id)],
            "market_id": market_id,
            "market_question": market_question,
            "trade_date": str(trade_date),
            "investment_debate_state": PMInvestDebateState(
                {
                    "yes_history": "",
                    "no_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "risk_debate_state": PMRiskDebateState(
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
            "event_report": "",
            "odds_report": "",
            "information_report": "",
            "sentiment_report": "",
        }

    def get_graph_args(self, callbacks: Optional[List] = None) -> Dict[str, Any]:
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
