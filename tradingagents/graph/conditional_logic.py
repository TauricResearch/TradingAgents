# TradingAgents/graph/conditional_logic.py

from tradingagents.agents.utils.agent_states import AgentState


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    @staticmethod
    def _has_tool_calls(message) -> bool:
        """Return True when ``message`` exposes non-empty tool calls.

        Analyst branches can end with placeholder ``HumanMessage`` instances
        during cleanup/synchronization. Those messages do not implement a
        ``tool_calls`` attribute, so routing must treat them the same as
        "no tool calls" instead of raising ``AttributeError``.
        """
        return bool(getattr(message, "tool_calls", None))

    def should_continue_market(self, state: AgentState):
        """Determine if market analysis should continue."""
        messages = state["market_messages"]
        last_message = messages[-1]
        if self._has_tool_calls(last_message):
            return "tools_market"
        return "Msg Clear Market"

    def should_continue_social(self, state: AgentState):
        """Determine if social media analysis should continue."""
        messages = state["sentiment_messages"]
        last_message = messages[-1]
        if self._has_tool_calls(last_message):
            return "tools_social"
        return "Msg Clear Social"

    def should_continue_news(self, state: AgentState):
        """Determine if news analysis should continue."""
        messages = state["news_messages"]
        last_message = messages[-1]
        if self._has_tool_calls(last_message):
            return "tools_news"
        return "Msg Clear News"

    def should_continue_fundamentals(self, state: AgentState):
        """Determine if fundamentals analysis should continue."""
        messages = state["fundamentals_messages"]
        last_message = messages[-1]
        if self._has_tool_calls(last_message):
            return "tools_fundamentals"
        return "Msg Clear Fundamentals"

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""

        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):  # 3 rounds of back-and-forth between 2 agents
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        if (
            state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
        ):  # 3 rounds of back-and-forth between 3 agents
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
