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
        """Create the initial state for the agent graph with validation."""
        if not company_name or not isinstance(company_name, str):
            raise ValueError(f"Invalid company_name: {company_name}")

        if not trade_date or not isinstance(trade_date, str):
            raise ValueError(f"Invalid trade_date: {trade_date}")

        from datetime import datetime
        try:
            parsed_date = datetime.strptime(trade_date, "%Y-%m-%d")
            if parsed_date.year < 1990 or parsed_date.year > 2030:
                raise ValueError(f"Trade date out of reasonable range: {trade_date}")
        except ValueError as e:
            raise ValueError(f"Invalid date format. Expected YYYY-MM-DD, got: {trade_date}") from e

        company_clean = company_name.strip().upper()
        if len(company_clean) < 1 or len(company_clean) > 10:
            raise ValueError(f"Company name must be 1-10 characters: {company_name}")

        return {
            "messages": [("human", company_clean)],
            "company_of_interest": company_clean,
            "trade_date": trade_date,
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
        }

    def get_graph_args(self) -> Dict[str, Any]:
        """Get arguments for the graph invocation."""
        return {
            "stream_mode": "values",
            "config": {"recursion_limit": self.max_recur_limit},
        }
