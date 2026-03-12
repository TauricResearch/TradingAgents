# TradingAgents/graph/propagation.py

from typing import Dict, Any, List, Optional


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100):
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        screening_context: str = "",
        portfolio_context: str = "",
    ) -> Dict[str, Any]:
        """Create the initial state for the swing trading graph."""
        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "trade_date": str(trade_date),
            "market_report": "",
            "fundamentals_report": "",
            "news_report": "",
            "screening_context": screening_context,
            "portfolio_context": portfolio_context,
            "trader_decision": "",
            "swing_order": "",
        }

    def get_graph_args(self, callbacks: Optional[List] = None) -> Dict[str, Any]:
        """Get arguments for the graph invocation."""
        config = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "values",
            "config": config,
        }
