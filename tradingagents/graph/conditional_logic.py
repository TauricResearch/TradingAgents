import logging

from tradingagents.agents.debate_judgments import (
    DEFAULT_POLICY,
    DebatePolicy,
    converged,
    new_argument,
    worth_judging,
)
from tradingagents.agents.state import AgentState

logger = logging.getLogger(__name__)

# Debate -> (state key, speakers per round).
DEBATES = {
    "investment": ("investment_debate_state", 2),
    "risk": ("risk_debate_state", 3),
}


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(
        self,
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        debate_policy: DebatePolicy = DEFAULT_POLICY,
    ):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
        self.debate_policy = debate_policy

    def _max_rounds(self, debate: str) -> int:
        return self.max_debate_rounds if debate == "investment" else self.max_risk_discuss_rounds

    def judge_turns(self, node, debate: str):
        """Wrap a debater node so each turn records whether it added anything new.

        The turn's P(new argument) from Jev is appended to the debate state's
        ``new_argument`` list, or None for a turn whose answer could not end the
        debate (see ``worth_judging``) or when Jev is off or failing. The routers
        read the list; without Jev every entry is None and the debate runs its
        configured rounds, as before.
        """
        key, speakers = DEBATES[debate]
        max_rounds = self._max_rounds(debate)
        policy = self.debate_policy

        def judged_node(state):
            update = node(state)
            before, after = state[key], update[key]
            prior, history = before.get("history", ""), after["history"]
            score = None
            # Every debater appends its turn to ``history``; what follows ``prior`` is the turn.
            if worth_judging(after["count"], speakers, max_rounds, policy) and history.startswith(prior):
                score = new_argument(prior.strip(), history[len(prior):].strip())
            after["new_argument"] = [*(before.get("new_argument") or []), score]
            return update

        return judged_node

    def _converged(self, debate: str, debate_state) -> bool:
        _, speakers = DEBATES[debate]
        if not converged(debate_state, speakers, self.debate_policy):
            return False
        logger.info(
            "%s debate converged after round %d of %d; skipping the rest",
            debate.capitalize(), debate_state["count"] // speakers, self._max_rounds(debate),
        )
        return True

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue.

        Ends after ``max_debate_rounds`` rounds, or sooner when a round converged.
        """
        debate = state["investment_debate_state"]
        if (
            debate["count"] >= 2 * self.max_debate_rounds  # each round: bull, then bear
            or self._converged("investment", debate)
        ):
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue.

        Ends after ``max_risk_discuss_rounds`` rounds, or sooner when a round converged.
        """
        debate = state["risk_debate_state"]
        if (
            debate["count"] >= 3 * self.max_risk_discuss_rounds  # each round: all three analysts
            or self._converged("risk", debate)
        ):
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
