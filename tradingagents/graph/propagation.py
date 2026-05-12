# TradingAgents/graph/propagation.py

import logging
from typing import Dict, Any, List, Optional
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)

logger = logging.getLogger(__name__)


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        past_context: str = "",
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create the initial state for the agent graph."""
        # Build portfolio context
        portfolio_context = ""
        _cfg = config or {}
        if _cfg.get("portfolio_enabled", True):
            try:
                from tradingagents.portfolio import PortfolioStore, build_portfolio_context
                portfolio_path = _cfg.get("portfolio_path", "") or None
                portfolio_store = PortfolioStore(portfolio_path=portfolio_path)
                portfolio_context = build_portfolio_context(company_name, portfolio_store)
            except Exception:
                logger.debug("Portfolio context unavailable, continuing without it", exc_info=True)
                portfolio_context = ""

        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "trade_date": str(trade_date),
            "past_context": past_context,
            "portfolio_context": portfolio_context,
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
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "values",
            "config": config,
        }
