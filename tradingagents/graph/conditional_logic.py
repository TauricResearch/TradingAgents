# TradingAgents/graph/conditional_logic.py

from tradingagents.agents.utils.agent_states import AgentState
from .node_names import NodeNames


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(
        self,
        max_debate_rounds: int = 1,
        max_risk_discuss_rounds: int = 1,
        n_research_debaters: int = 2,
        n_risk_debaters: int = 3,
    ):
        """Initialize with configuration parameters.

        Args:
            max_debate_rounds: Number of full debate cycles for bull/bear research.
            max_risk_discuss_rounds: Number of full cycles for risk analysis.
            n_research_debaters: How many agents participate in the research debate.
                Derived automatically so adding a new debater doesn't require
                touching the limit formula.
            n_risk_debaters: How many agents participate in the risk debate.
        """
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
        # Pre-compute limits so routing methods stay O(1) and formula is in one place.
        self._research_limit = n_research_debaters * max_debate_rounds
        self._risk_limit = n_risk_debaters * max_risk_discuss_rounds

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if investment debate should continue."""
        if state["investment_debate_state"]["count"] >= self._research_limit:
            return NodeNames.RESEARCH_MANAGER
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return NodeNames.BEAR_RESEARCHER
        return NodeNames.BULL_RESEARCHER

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        if state["risk_debate_state"]["count"] >= self._risk_limit:
            return NodeNames.PORTFOLIO_MANAGER
        speaker = state["risk_debate_state"]["latest_speaker"]
        if speaker.startswith("Aggressive"):
            return NodeNames.CONSERVATIVE_ANALYST
        if speaker.startswith("Conservative"):
            return NodeNames.NEUTRAL_ANALYST
        return NodeNames.AGGRESSIVE_ANALYST
