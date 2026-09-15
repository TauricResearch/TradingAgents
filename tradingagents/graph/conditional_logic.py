from langgraph.graph import END

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS, AnalystNodeSpec


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    def should_continue_market(self, state: AgentState):
        """Determine if market analysis should continue."""
        messages = state.get("market_messages") or state.get("messages", [])
        last_message = messages[-1] if messages else None
        if last_message and getattr(last_message, "tool_calls", None):
            return "tools_market"
        return "analyst_barrier"

    def should_continue_social(self, state: AgentState):
        """Determine if sentiment analysis should continue."""
        messages = state.get("sentiment_messages") or state.get("messages", [])
        last_message = messages[-1] if messages else None
        if last_message and getattr(last_message, "tool_calls", None):
            return "tools_social"
        return "analyst_barrier"

    def should_continue_news(self, state: AgentState):
        """Determine if news analysis should continue."""
        messages = state.get("news_messages") or state.get("messages", [])
        last_message = messages[-1] if messages else None
        if last_message and getattr(last_message, "tool_calls", None):
            return "tools_news"
        return "analyst_barrier"

    def should_continue_fundamentals(self, state: AgentState):
        """Determine if fundamentals analysis should continue."""
        messages = state.get("fundamentals_messages") or state.get("messages", [])
        last_message = messages[-1] if messages else None
        if last_message and getattr(last_message, "tool_calls", None):
            return "tools_fundamentals"
        return "analyst_barrier"

    def should_continue_barrier(
        self, state: AgentState, plan_specs: list[AnalystNodeSpec] | None = None
    ) -> str:
        """Check if all active analyst reports are complete before proceeding to debate."""
        specs = plan_specs if plan_specs is not None else list(ANALYST_NODE_SPECS.values())
        if all(bool(state.get(spec.report_key)) for spec in specs):
            return "Bull Researcher"
        return END

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
