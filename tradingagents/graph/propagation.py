# TradingAgents/graph/propagation.py

from typing import Dict, Any
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self, company_name: str, trade_date: str
    ) -> Dict[str, Any]:
        """Create the initial state for the agent graph."""
        company_value = (company_name or "").strip()
        trade_value = str(trade_date) if trade_date else ""
        initial_prompt = company_value or "Portfolio orchestration start"
        return {
            "messages": [("human", initial_prompt)],
            "company_of_interest": company_value,
            "trade_date": trade_value,
            "target_ticker": company_value,
            "investment_debate_state": InvestDebateState(
                {"history": "", "current_response": "", "count": 0}
            ),
            "risk_debate_state": RiskDebateState(
                {
                    "history": "",
                    "current_risky_response": "",
                    "current_safe_response": "",
                    "current_neutral_response": "",
                    "count": 0,
                }
            ),
            "market_report": "",
            "fundamentals_report": "",
            "sentiment_report": "",
            "news_report": "",
            "investment_plan": "",
            "trader_investment_plan": "",
            "final_trade_decision": "",
            "portfolio_profile": {},
            "portfolio_summary": "",
            "orchestrator_status": "not_started",
            "alpaca_account_text": "",
            "alpaca_positions_text": "",
            "alpaca_orders_text": "",
            "orchestrator_hypotheses": [],
            "active_hypothesis": None,
            "scheduled_analysts": [],
            "scheduled_analysts_plan": [],
            "orchestrator_action": "",
            "action_queue": [],
            "next_directive": "stop",
            "next_node": "",
            "portfolio_account_summary": {},
            "portfolio_positions_summary": [],
            "planner_plan": {},
            "planner_notes": "",
            "orchestrator_pending_tickers": [],
            "orchestrator_focus_symbols": [],
            "orchestrator_quick_signals": {},
            "orchestrator_market_data": {},
            "orchestrator_ticker_plans": {},
            "orchestrator_focus_override": [],
        }

    def get_graph_args(self) -> Dict[str, Any]:
        """Get arguments for the graph invocation."""
        return {
            "stream_mode": "values",
            "config": {"recursion_limit": self.max_recur_limit},
        }
