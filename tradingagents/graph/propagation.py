# TradingAgents/graph/propagation.py

from typing import Any

from tradingagents.agents.utils.agent_states import (
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.instruments import resolve_instrument


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit: int = 100):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        run_id: str,
        portfolio_context: str = "candidate",
        scanner_context_packet: str = "",
        scanner_graph_context_text: str = "",
        market_report: str = "",
        market_report_structured: dict[str, Any] | None = None,
        macro_regime_report: str = "",
    ) -> dict[str, Any]:
        """Create the initial state for the agent graph."""
        instrument = resolve_instrument(company_name, source_context="trading_graph")
        return {
            "messages": [("human", company_name)],
            "run_id": str(run_id),
            "company_of_interest": company_name,
            "trade_date": str(trade_date),
            "portfolio_context": portfolio_context,
            "scanner_context_packet": scanner_context_packet,
            "scanner_graph_context_text": scanner_graph_context_text,
            "instrument_key": instrument.instrument_key,
            "asset_class": instrument.asset_class,
            "instrument_type": instrument.instrument_type,
            "is_etf": instrument.is_etf,
            "is_inverse": instrument.is_inverse,
            "is_leveraged": instrument.is_leveraged,
            "analysis_status": "pending",
            "terminal_action": "",
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "summary": "",
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
                    "summary": "",
                    "latest_speaker": "",
                    "current_aggressive_response": "",
                    "current_conservative_response": "",
                    "current_neutral_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "market_report": market_report,
            "market_report_structured": market_report_structured or {},
            "fundamentals_report": "",
            "fundamentals_report_structured": {},
            "sentiment_report": "",
            "news_report": "",
            "news_report_structured": {},
            "investment_plan": "",
            "rm_consistency_status": "",
            "rm_consistency_flags": [],
            "consistency_violations": [],
            "_rm_consistency_attempt": 0,
            "trader_investment_plan": "",
            "final_trade_decision": "",
            "macro_regime_report": macro_regime_report,
            "research_packet_summary": "",
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
