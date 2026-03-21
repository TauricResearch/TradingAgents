from typing import Dict, Any, List, Optional

from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)


class Propagator:
    """Handles state initialization and graph argument configuration."""

    def __init__(self, max_recur_limit=100):
        self.max_recur_limit = max_recur_limit

    def create_initial_state(self, event_id, event_question, trade_date):
        """Create the initial agent state for a Polymarket event analysis."""
        return {
            "messages": [("human", event_question)],
            "event_id": event_id,
            "event_question": event_question,
            "trade_date": str(trade_date),
            "sender": "",
            "odds_report": "",
            "sentiment_report": "",
            "news_report": "",
            "event_report": "",
            "investment_debate_state": {
                "yes_history": "",
                "no_history": "",
                "timing_history": "",
                "history": "",
                "current_yes_response": "",
                "current_no_response": "",
                "current_timing_response": "",
                "latest_speaker": "",
                "judge_decision": "",
                "count": 0,
            },
            "investment_plan": "",
            "trader_plan": "",
            "risk_debate_state": {
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
            },
            "final_decision": "",
        }

    def get_graph_args(self, callbacks=None):
        """Get the arguments for graph invocation."""
        config = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "values",
            "config": config,
        }
