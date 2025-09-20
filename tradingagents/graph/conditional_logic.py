# TradingAgents/graph/conditional_logic.py

from tradingagents.agents.utils.agent_states import AgentState


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    def should_continue_market(self, state: AgentState):
        """Determine if market analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_market"
        return "Msg Clear Market"

    def should_continue_social(self, state: AgentState):
        """Determine if social media analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_social"
        return "Msg Clear Social"

    def should_continue_news(self, state: AgentState):
        """Determine if news analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_news"
        return "Msg Clear News"

    def should_continue_fundamentals(self, state: AgentState):
        """Determine if fundamentals analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_fundamentals"
        return "Msg Clear Fundamentals"

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue with proper validation."""
        if not state or "investment_debate_state" not in state:
            return "Research Manager"

        debate_state = state["investment_debate_state"]
        count = debate_state.get("count", 0)
        current_response = debate_state.get("current_response", "")

        if not isinstance(count, int) or count < 0:
            return "Research Manager"

        if count >= 2 * self.max_debate_rounds:
            return "Research Manager"

        if isinstance(current_response, str) and current_response.strip():
            if current_response.upper().startswith("BULL"):
                return "Bear Researcher"

        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue with proper validation."""
        if not state or "risk_debate_state" not in state:
            return "Risk Judge"

        risk_state = state["risk_debate_state"]
        count = risk_state.get("count", 0)
        latest_speaker = risk_state.get("latest_speaker", "")

        if not isinstance(count, int) or count < 0:
            return "Risk Judge"

        if count >= 3 * self.max_risk_discuss_rounds:
            return "Risk Judge"

        if isinstance(latest_speaker, str) and latest_speaker.strip():
            speaker_upper = latest_speaker.upper()
            if speaker_upper.startswith("RISKY"):
                return "Safe Analyst"
            elif speaker_upper.startswith("SAFE"):
                return "Neutral Analyst"

        return "Risky Analyst"
