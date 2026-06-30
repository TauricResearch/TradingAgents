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
        if getattr(last_message, 'tool_calls', None):
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
        if getattr(last_message, 'tool_calls', None):
            return "tools_social"
        return "Msg Clear Sentiment"

    def should_continue_news(self, state: AgentState):
        """Determine if news analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if getattr(last_message, 'tool_calls', None):
            return "tools_news"
        return "Msg Clear News"

    def should_continue_fundamentals(self, state: AgentState):
        """Determine if fundamentals analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if getattr(last_message, 'tool_calls', None):
            return "tools_fundamentals"
        return "Msg Clear Fundamentals"

    def should_continue_technical(self, state: AgentState):
        """Determine if technical analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if getattr(last_message, 'tool_calls', None):
            return "tools_technical"
        return "Msg Clear Technical"

    def should_continue_quant(self, state: AgentState):
        """Determine if quantitative analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if getattr(last_message, 'tool_calls', None):
            return "tools_quant"
        return "Msg Clear Quant"

    def should_continue_options(self, state: AgentState):
        """Determine if options analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if getattr(last_message, 'tool_calls', None):
            return "tools_options"
        return "Msg Clear Options"

    def should_continue_alternative(self, state: AgentState):
        """Determine if alternative data analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if getattr(last_message, 'tool_calls', None):
            return "tools_alternative"
        return "Msg Clear Alternative"

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
