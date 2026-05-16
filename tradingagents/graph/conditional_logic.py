# TradingAgents/graph/conditional_logic.py

from tradingagents.agents.utils.agent_states import AgentState


_ANALYST_MESSAGES_KEY = {
    "market": "market_messages",
    "social": "sentiment_messages",
    "news": "news_messages",
    "fundamentals": "fundamentals_messages",
}


def _last_message_wants_tools(state: AgentState, messages_key: str) -> bool:
    messages = state.get(messages_key) or []
    if not messages:
        return False
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None)
    return bool(tool_calls)


def _count_tool_calls(state: AgentState, messages_key: str) -> int:
    """Count tool calls already made on this analyst's transcript."""
    count = 0
    for msg in state.get(messages_key) or []:
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            count += len(tool_calls)
    return count


class ConditionalLogic:
    """Handles conditional logic for determining graph flow.

    The four ``should_continue_<analyst>`` methods support both graph
    topologies: in the legacy serial flow they read from the shared
    ``messages`` channel; in the parallel/fusion flow they read from
    the analyst's dedicated ``*_messages`` channel. The constructor
    flag ``parallel_analysts`` picks which one.

    The ``max_analyst_tool_calls`` cap is an optional safety net used
    primarily in the parallel flow, where a runaway analyst is a cost
    hit (concurrent providers, no serial backpressure). Set to ``None``
    to disable.
    """

    def __init__(
        self,
        max_debate_rounds: int = 1,
        max_risk_discuss_rounds: int = 1,
        *,
        parallel_analysts: bool = False,
        max_analyst_tool_calls: int | None = None,
    ):
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
        self.parallel_analysts = parallel_analysts
        self.max_analyst_tool_calls = max_analyst_tool_calls

    def _analyst_route(self, state: AgentState, analyst: str) -> str:
        """Pick the next node for an analyst tool loop.

        Returns one of ``tools_<analyst>``, ``Msg Clear <Analyst>``, or
        ``Extract <Analyst>`` depending on whether tools are pending,
        the budget is exhausted, or the analyst is done. The exact
        destination names depend on which graph topology is active —
        callers pass the names through the conditional-edge mapping.
        """
        messages_key = (
            _ANALYST_MESSAGES_KEY[analyst]
            if self.parallel_analysts
            else "messages"
        )
        wants_tools = _last_message_wants_tools(state, messages_key)
        budget_hit = (
            self.max_analyst_tool_calls is not None
            and _count_tool_calls(state, messages_key) >= self.max_analyst_tool_calls
        )

        if wants_tools and not budget_hit:
            return f"tools_{analyst}"
        # Legacy serial flow drops into a Msg Clear node before the next
        # analyst runs; parallel flow drops into an Extract Signal node
        # that produces the AnalystSignal for SignalFusion.
        if self.parallel_analysts:
            return f"Extract {_ANALYST_LABEL[analyst]}"
        return f"Msg Clear {_ANALYST_LABEL[analyst]}"

    def should_continue_market(self, state: AgentState):
        return self._analyst_route(state, "market")

    def should_continue_social(self, state: AgentState):
        return self._analyst_route(state, "social")

    def should_continue_news(self, state: AgentState):
        return self._analyst_route(state, "news")

    def should_continue_fundamentals(self, state: AgentState):
        return self._analyst_route(state, "fundamentals")

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


# Human-readable labels for use in graph node names.
# Note: the "social" wire-value still maps to "Social" in the graph node
# name (and the existing "Msg Clear Social" node) for back-compat with
# saved checkpoints; the underlying agent is the renamed sentiment one.
_ANALYST_LABEL = {
    "market": "Market",
    "social": "Social",
    "news": "News",
    "fundamentals": "Fundamentals",
}