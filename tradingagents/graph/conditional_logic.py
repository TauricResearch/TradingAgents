"""Conditional routing logic for the trading agents graph."""


class ConditionalLogic:
    """Handles conditional routing decisions in the graph."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    def should_continue_odds(self, state):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_odds"
        return "Msg Clear Odds"

    def should_continue_social(self, state):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_social"
        return "Msg Clear Social"

    def should_continue_news(self, state):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_news"
        return "Msg Clear News"

    def should_continue_event(self, state):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_event"
        return "Msg Clear Event"

    def should_continue_debate(self, state):
        """Route 3-way YES/NO/Timing debate. Mirrors risk debate pattern."""
        count = state["investment_debate_state"]["count"]
        if count >= 3 * self.max_debate_rounds:
            return "Research Manager"
        latest = state["investment_debate_state"].get("latest_speaker", "")
        if latest.startswith("YES"):
            return "NO Advocate"
        elif latest.startswith("NO"):
            return "Timing Advocate"
        else:
            # Initial entry or after Timing -> start with YES
            return "YES Advocate"

    def should_continue_risk_analysis(self, state):
        """Route 3-way risk debate. Unchanged from original."""
        count = state["risk_debate_state"]["count"]
        if count >= 3 * self.max_risk_discuss_rounds:
            return "Risk Judge"
        latest = state["risk_debate_state"].get("latest_speaker", "")
        if latest.startswith("Aggressive"):
            return "Conservative Analyst"
        elif latest.startswith("Conservative"):
            return "Neutral Analyst"
        else:
            return "Aggressive Analyst"
