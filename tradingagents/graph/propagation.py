# TradingAgents/graph/propagation.py

from typing import Any

from tradingagents.agents.utils.agent_states import (
    InvestDebateState,
    RiskDebateState,
)


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
        evidence_ledger: dict[str, Any] | None = None,
        evidence_summary: str = "",
        quantitative_anchors: list[dict[str, Any]] | None = None,
        math_guardrail_events: list[dict[str, Any]] | None = None,
        citation_verification: dict[str, Any] | None = None,
        evidence_warnings: list[str] | None = None,
        evidence_strict_mode: str = "warn",
        evidence_strict_blocked: bool = False,
        evidence_decision_status: str = "actionable",
        evidence_actionable: bool = True,
        evidence_blocking_reasons: list[str] | None = None,
        original_final_trade_decision: str | None = None,
    ) -> dict[str, Any]:
        """Create the initial state for the agent graph.

        ``instrument_context`` is the deterministic ticker-identity string
        resolved once at run start (see
        ``TradingAgentsGraph.resolve_instrument_context``). When empty, agents
        fall back to ticker-only context via
        ``get_instrument_context_from_state``.
        """
        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "asset_type": asset_type,
            "instrument_context": instrument_context,
            "trade_date": str(trade_date),
            "past_context": past_context,
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
            "evidence_ledger": evidence_ledger or {"items": []},
            "evidence_summary": evidence_summary,
            "quantitative_anchors": list(quantitative_anchors or []),
            "math_guardrail_events": list(math_guardrail_events or []),
            "citation_verification": citation_verification,
            "evidence_warnings": list(evidence_warnings or []),
            "evidence_strict_mode": evidence_strict_mode,
            "evidence_strict_blocked": evidence_strict_blocked,
            "evidence_decision_status": evidence_decision_status,
            "evidence_actionable": evidence_actionable,
            "evidence_blocking_reasons": list(evidence_blocking_reasons or []),
            "original_final_trade_decision": original_final_trade_decision,
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
