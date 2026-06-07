# TradingAgents/graph/conditional_logic.py

from tradingagents.agents.utils.agent_states import AgentState


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    def _should_continue_tool_round(self, state: AgentState, tool_node: str, clear_node: str):
        messages = state["messages"]
        last_message = messages[-1]
        if getattr(last_message, "tool_calls", None):
            return tool_node
        return clear_node

    def should_continue_market(self, state: AgentState):
        """Determine if market analysis should continue."""
        return self._should_continue_tool_round(state, "tools_market", "Msg Clear Market")

    def should_continue_social(self, state: AgentState):
        """Determine if sentiment-analyst tool round should continue.

        Method name keeps the legacy ``social`` suffix to match the
        ``AnalystType.SOCIAL = "social"`` wire value (saved-config
        back-compat); the returned ``clear_node`` label uses the v0.2.5
        rename so it matches the node registered by the execution plan.
        """
        return self._should_continue_tool_round(state, "tools_social", "Msg Clear Sentiment")

    def should_continue_news(self, state: AgentState):
        """Determine if news analysis should continue."""
        return self._should_continue_tool_round(state, "tools_news", "Msg Clear News")

    def should_continue_fundamentals(self, state: AgentState):
        """Determine if fundamentals analysis should continue."""
        return self._should_continue_tool_round(state, "tools_fundamentals", "Msg Clear Fundamentals")

    def should_continue_india_market(self, state: AgentState):
        return self._should_continue_tool_round(state, "tools_india_market", "Msg Clear India Market")

    def should_continue_india_fundamentals(self, state: AgentState):
        return self._should_continue_tool_round(state, "tools_india_fundamentals", "Msg Clear India Fundamentals")

    def should_continue_india_news_filings(self, state: AgentState):
        return self._should_continue_tool_round(state, "tools_india_news_filings", "Msg Clear India News Filings")

    def should_continue_india_macro_policy(self, state: AgentState):
        return self._should_continue_tool_round(state, "tools_india_macro_policy", "Msg Clear India Macro Policy")

    def should_continue_india_flows(self, state: AgentState):
        return self._should_continue_tool_round(state, "tools_india_flows", "Msg Clear India Flows")

    def should_continue_india_sentiment(self, state: AgentState):
        return self._should_continue_tool_round(state, "tools_india_sentiment", "Msg Clear India Sentiment")

    def should_continue_india_compliance(self, state: AgentState):
        return self._should_continue_tool_round(state, "tools_india_compliance", "Msg Clear India Compliance")

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
