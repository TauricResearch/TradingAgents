# TradingAgents/graph/conditional_logic.py

from typing import Callable
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.critical_abort import (
    report_has_critical_abort,
    state_has_critical_abort,
)
from tradingagents.constants import CRITICAL_ABORT_NODE


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    def _check_critical_abort(self, state: AgentState, report_field: str) -> bool:
        """Check if a report contains [CRITICAL ABORT] trigger."""
        report = state.get(report_field, "")
        if not report:
            return False
        # Deliberately require the explicit leading marker. Bearish language
        # such as "sell", "strong sell", or "avoid" must still go through the
        # normal debate/risk flow unless the analyst emitted a hard-stop abort
        # marker at the start of the report.
        return report_has_critical_abort(report)

    @staticmethod
    def make_should_continue(tool_name: str, msg_clear: str) -> Callable[[AgentState], str]:
        """Factory for analyzer continuation logic."""
        def should_continue(state: AgentState) -> str:
            messages = state["messages"]
            last_message = messages[-1]
            if last_message.tool_calls:
                return tool_name
            return msg_clear
        return should_continue

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""
        # Only the explicit CRITICAL ABORT marker bypasses debate.
        if state_has_critical_abort(
            state, "market_report", "news_report", "fundamentals_report"
        ):
            return CRITICAL_ABORT_NODE

        if state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds:
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        # Only the explicit CRITICAL ABORT marker bypasses risk analysis.
        if state_has_critical_abort(
            state, "market_report", "news_report", "fundamentals_report"
        ):
            return CRITICAL_ABORT_NODE

        if state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds:
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
