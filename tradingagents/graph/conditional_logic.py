# TradingAgents/graph/conditional_logic.py

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.critical_abort import has_abort
from tradingagents.constants import CRITICAL_ABORT_NODE


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds: int = 1, max_risk_discuss_rounds: int = 1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""
        if has_abort(state):
            return CRITICAL_ABORT_NODE

        # Defensive: handle missing or incomplete investment_debate_state
        debate_state = state.get("investment_debate_state")
        if not debate_state:
            # No debate state means we should end debate
            return "Research Manager"

        count = debate_state.get("count")
        if count is None or count >= 2 * self.max_debate_rounds:
            return "Research Manager"

        current_response = debate_state.get("current_response", "")
        if not current_response:
            # Missing current_response; default to Bull to start debate
            return "Bull Researcher"

        if current_response.startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        if has_abort(state):
            return CRITICAL_ABORT_NODE

        # Defensive: handle missing or incomplete risk_debate_state
        risk_state = state.get("risk_debate_state")
        if not risk_state:
            # No risk state means we should end risk analysis
            return "Portfolio Manager"

        count = risk_state.get("count")
        if count is None or count >= 3 * self.max_risk_discuss_rounds:
            return "Portfolio Manager"

        latest_speaker = risk_state.get("latest_speaker", "")
        if not latest_speaker:
            # Missing latest_speaker; default to starting with Aggressive
            return "Aggressive Analyst"

        if latest_speaker.startswith("Aggressive"):
            return "Conservative Analyst"
        if latest_speaker.startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
