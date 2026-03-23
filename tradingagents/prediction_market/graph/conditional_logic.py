# TradingAgents/prediction_market/graph/conditional_logic.py

from tradingagents.prediction_market.agents.utils.pm_agent_states import PMAgentState


class PMConditionalLogic:
    """Handles conditional logic for determining prediction market graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    def should_continue_event(self, state: PMAgentState):
        """Determine if event analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_event"
        return "Msg Clear Event"

    def should_continue_odds(self, state: PMAgentState):
        """Determine if odds analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_odds"
        return "Msg Clear Odds"

    def should_continue_information(self, state: PMAgentState):
        """Determine if information analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_information"
        return "Msg Clear Information"

    def should_continue_sentiment(self, state: PMAgentState):
        """Determine if sentiment analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_sentiment"
        return "Msg Clear Sentiment"

    def should_continue_debate(self, state: PMAgentState) -> str:
        """Determine if YES/NO debate should continue."""

        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):  # rounds of back-and-forth between 2 agents
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("YES"):
            return "NO Researcher"
        return "YES Researcher"

    def should_continue_risk_analysis(self, state: PMAgentState) -> str:
        """Determine if risk analysis should continue."""
        if (
            state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
        ):  # rounds of back-and-forth between 3 agents
            return "Risk Judge"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
