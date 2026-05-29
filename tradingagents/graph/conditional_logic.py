# TradingAgents/graph/conditional_logic.py

from langchain_core.messages import AIMessage

from tradingagents.agents.utils.agent_states import AgentState


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    DEFAULT_ANALYST_TOOL_CAP = {
        "market": 3,
        "social": 3,
        "news": 3,
        "fundamentals": 4,
    }

    def __init__(
        self,
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        max_analyst_tool_calls=None,
    ):
        """Initialize with configuration parameters.

        max_analyst_tool_calls bounds how many tool-calling rounds each
        analyst may perform before being forced to finalize without tools.
        Without this, a misbehaving LLM can loop until the global
        recursion_limit fires and the whole graph crashes mid-backtest.
        """
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
        self.max_analyst_tool_calls = {
            **self.DEFAULT_ANALYST_TOOL_CAP,
            **(max_analyst_tool_calls or {}),
        }

    def _route_analyst(self, state: AgentState, analyst_type: str) -> str:
        capitalized = analyst_type.capitalize()
        last_message = state["messages"][-1]
        if not getattr(last_message, "tool_calls", None):
            return f"Msg Clear {capitalized}"

        cap = self.max_analyst_tool_calls.get(analyst_type, 3)
        rounds = sum(
            1 for m in state["messages"]
            if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
        )
        if rounds > cap:
            return f"Force Finalize {capitalized}"
        return f"tools_{analyst_type}"

    def should_continue_market(self, state: AgentState):
        return self._route_analyst(state, "market")

    def should_continue_social(self, state: AgentState):
        return self._route_analyst(state, "social")

    def should_continue_news(self, state: AgentState):
        return self._route_analyst(state, "news")

    def should_continue_fundamentals(self, state: AgentState):
        return self._route_analyst(state, "fundamentals")

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""

        if (
            state["investment_debate_state"]["count"] >= 1 * self.max_debate_rounds
        ):  # 3 rounds of back-and-forth between 2 agents
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        if (
            state["risk_debate_state"]["count"] >= 1 * self.max_risk_discuss_rounds
        ):  # 3 rounds of back-and-forth between 3 agents
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
