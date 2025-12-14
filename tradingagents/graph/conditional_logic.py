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

    def should_continue_screening(self, state: AgentState):
        """Determine if screening should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        
        # Check for tool call limit to prevent recursion errors
        tool_call_count = 0
        for m in reversed(messages):
            if m.type == "human":
                break
            if m.type == "ai" and m.tool_calls:
                tool_call_count += 1
        
        if last_message.tool_calls:
            if tool_call_count > 3:
                print(f"--- Screening Agent Tool Limit Reached ({tool_call_count}) ---")
                return "Msg Clear Market" # Force move to Parser
            return "tools_screening"
        return "Msg Clear Market" # Re-using this to map to Parser in setup.py

    def should_continue_pump_detection(self, state: AgentState):
        """Determine if pump detection should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        
        # Check for tool call limit
        tool_call_count = 0
        for m in reversed(messages):
            if m.type == "human":
                break
            if m.type == "ai" and m.tool_calls:
                tool_call_count += 1
                
        if last_message.tool_calls:
            if tool_call_count > 3:
                print(f"--- Pump Discovery Tool Limit Reached ({tool_call_count}) ---")
                return "Msg Clear Market" # Force move to Parser
            return "tools_pump_detection"
        return "Msg Clear Market" # Re-using this to map to Parser in setup.py

    def should_continue_social(self, state: AgentState):
        """Determine if social media analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_social"
        return "Msg Clear Social"

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
            return "Risk Judge"
        if state["risk_debate_state"]["latest_speaker"].startswith("Risky"):
            return "Safe Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Safe"):
            return "Neutral Analyst"
        return "Risky Analyst"
