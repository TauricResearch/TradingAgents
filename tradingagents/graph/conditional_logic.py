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
        """Determine if sentiment-analyst tool round should continue.

        Method name keeps the legacy ``social`` suffix to match the
        ``AnalystType.SOCIAL = "social"`` wire value (saved-config
        back-compat); the returned ``clear_node`` label uses the v0.2.5
        rename so it matches the node registered by the execution plan.
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_social"
        return "Msg Clear Sentiment"

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
        """Determine if debate should continue."""

        if self._investment_debate_is_complete(state):
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_after_bull_researcher(self, state: AgentState) -> str:
        """Determine the next node after the Bull Researcher."""
        if self._investment_debate_is_complete(state):
            return "Research Manager"
        return "Bear Researcher"

    def should_continue_after_bear_researcher(self, state: AgentState) -> str:
        """Determine the next node after the Bear Researcher."""
        if self._investment_debate_is_complete(state):
            return "Research Manager"
        return "Bull Researcher"

    def _investment_debate_is_complete(self, state: AgentState) -> bool:
        return state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        if self._risk_analysis_is_complete(state):
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"

    def should_continue_after_aggressive_analyst(self, state: AgentState) -> str:
        """Determine the next node after the Aggressive Analyst."""
        if self._risk_analysis_is_complete(state):
            return "Portfolio Manager"
        return "Conservative Analyst"

    def should_continue_after_conservative_analyst(self, state: AgentState) -> str:
        """Determine the next node after the Conservative Analyst."""
        if self._risk_analysis_is_complete(state):
            return "Portfolio Manager"
        return "Neutral Analyst"

    def should_continue_after_neutral_analyst(self, state: AgentState) -> str:
        """Determine the next node after the Neutral Analyst."""
        if self._risk_analysis_is_complete(state):
            return "Portfolio Manager"
        return "Aggressive Analyst"

    def _risk_analysis_is_complete(self, state: AgentState) -> bool:
        return state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
