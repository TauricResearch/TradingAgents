"""
Enhanced Conditional Logic with Rejection Loops

Adds backward edges to send proposals back to agents if they fail validation.
"""

from tradingagents.agents.utils.agent_states import AgentState


class EnhancedConditionalLogic:
    """Handles conditional logic with rejection loops and quality checks."""
    
    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
    
    
    def should_continue_market(self, state: AgentState):
        """Determine if market analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if getattr(last_message, "tool_calls", None):
            return "tools_market"
        return "Msg Clear Market"

    def should_continue_social(self, state: AgentState):
        """Determine if social media analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if getattr(last_message, "tool_calls", None):
            return "tools_social"
        return "Msg Clear Social"

    def should_continue_news(self, state: AgentState):
        """Determine if news analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if getattr(last_message, "tool_calls", None):
            return "tools_news"
        return "Msg Clear News"

    def should_continue_fundamentals(self, state: AgentState):
        """Determine if fundamentals analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if getattr(last_message, "tool_calls", None):
            return "tools_fundamentals"
        return "Msg Clear Fundamentals"

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue (Legacy Support)."""
        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):  # 3 rounds of back-and-forth between 2 agents
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"
    
    
    # DEPRECATED: This method is no longer used in Star Topology
    # You can keep it for legacy support or delete it to keep code clean.
    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """
        [DEPRECATED]
        Previously handled Round-Robin routing for Risk Analysts.
        Replaced by Parallel Fan-Out in setup.py.
        """
        pass


    
    def should_continue_debate_with_validation(self, state: AgentState) -> str:
        """
        Determine if debate should continue WITH QUALITY CHECKS.
        
        This replaces the naive round-robin with actual validation.
        """
        debate_state = state["investment_debate_state"]
        
        # Check 1: Was last argument fact-checked and rejected?
        if debate_state.get("last_argument_invalid", False):
            # Send back to same agent to revise
            print(f"❌ REJECTED: {debate_state.get('rejection_reason', 'Invalid argument')}")
            print(f"   Sending back to {debate_state['latest_speaker']} for revision")
            
            # Route back to the agent that made the bad argument
            if debate_state["latest_speaker"] == "Bull":
                return "Bull Researcher"
            else:
                return "Bear Researcher"
        
        # Check 2: Has consensus been reached?
        if debate_state.get("consensus_reached", False):
            print("✅ CONSENSUS REACHED: Proceeding to Research Manager")
            return "Research Manager"
        
        # Check 3: Max rounds exceeded
        if debate_state["count"] >= 2 * self.max_debate_rounds:
            print(f"⏱️  MAX ROUNDS REACHED: {debate_state['count']} rounds")
            return "Research Manager"
        
        # Check 4: Confidence too low (force another round)
        if debate_state.get("confidence", 1.0) < 0.5:
            print(f"⚠️  LOW CONFIDENCE ({debate_state['confidence']:.1%}): Continuing debate")
            # Continue round-robin
            if debate_state["current_response"].startswith("Bull"):
                return "Bear Researcher"
            return "Bull Researcher"
        
        # Default: Round-robin
        if debate_state["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"
    
    def should_proceed_after_risk_gate(self, state: AgentState) -> str:
        """
        Determine next step after deterministic risk gate validation.
        
        This is a NEW node that checks mathematical risk validation.
        """
        risk_validation = state.get("risk_gate_result", {})
        
        # Check 1: Was trade rejected by risk gate?
        if not risk_validation.get("approved", False):
            rejection_reason = risk_validation.get("rejection_reason", "Unknown")
            
            # Determine severity
            if "CIRCUIT BREAKER" in rejection_reason:
                # Critical failure - halt trading
                print(f"🚨 CIRCUIT BREAKER TRIGGERED: {rejection_reason}")
                return "END"
            
            elif "DATA QUALITY" in rejection_reason:
                # Data issue - send back to analysts
                print(f"📊 DATA QUALITY FAILURE: {rejection_reason}")
                print("   Routing back to Market Analyst for data refresh")
                return "Market Analyst"
            
            elif "PORTFOLIO HEAT" in rejection_reason or "POSITION RISK" in rejection_reason:
                # Risk limit exceeded - send to Risk Manager for review
                print(f"⚠️  RISK LIMIT EXCEEDED: {rejection_reason}")
                print("   Routing to Risk Manager for position adjustment")
                return "Risk Manager Revision"
            
            else:
                # Generic rejection - log and hold
                print(f"❌ TRADE REJECTED: {rejection_reason}")
                return "END"
        
        # Check 2: Was position size overridden?
        if risk_validation.get("override_message"):
            print(f"🔧 {risk_validation['override_message']}")
        
        # Approved - proceed to execution
        print("✅ RISK GATE PASSED: Trade approved")
        return "Execute Trade"
    
    def should_continue_risk_analysis_with_validation(self, state: AgentState) -> str:
        """
        Enhanced risk analysis routing with validation.
        """
        risk_state = state["risk_debate_state"]
        
        # Check 1: Did any analyst provide mathematically invalid reasoning?
        if risk_state.get("invalid_reasoning_detected", False):
            # Send back to the analyst who made the error
            print(f"❌ INVALID REASONING: {risk_state.get('error_message', '')}")
            return risk_state["latest_speaker"]
        
        # Check 2: Max rounds
        if risk_state["count"] >= 3 * self.max_risk_discuss_rounds:
            return "Deterministic Risk Gate"  # NEW: Route to math validation
        
        # Round-robin
        if risk_state["latest_speaker"].startswith("Risky"):
            return "Safe Analyst"
        if risk_state["latest_speaker"].startswith("Safe"):
            return "Neutral Analyst"
        return "Risky Analyst"


# Integration example for trading_graph.py
"""
To integrate this into your graph:

1. Add the Deterministic Risk Gate node:
   workflow.add_node("Deterministic Risk Gate", deterministic_risk_gate_node)

2. Replace the edge from "Risk Judge" to END:
   # OLD:
   workflow.add_edge("Risk Judge", END)
   
   # NEW:
   workflow.add_conditional_edges(
       "Risk Judge",
       enhanced_logic.should_proceed_after_risk_gate,
       {
           "END": END,
           "Market Analyst": "Market Analyst",  # Data quality failure
           "Risk Manager Revision": "Risk Manager Revision",  # Risk limit exceeded
           "Execute Trade": "Execute Trade"  # Approved
       }
   )

3. Add backward edge for debate rejection:
   workflow.add_conditional_edges(
       "Bull Researcher",
       enhanced_logic.should_continue_debate_with_validation,
       {
           "Bear Researcher": "Bear Researcher",
           "Bull Researcher": "Bull Researcher",  # NEW: Rejection loop
           "Research Manager": "Research Manager",
       }
   )
"""
