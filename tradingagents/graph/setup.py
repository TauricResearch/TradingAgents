# TradingAgents/graph/setup.py

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import (
    AgentState, 
    SocialAnalystState, 
    NewsAnalystState, 
    FundamentalsAnalystState
)
from tradingagents.agents.data_registrar import create_data_registrar

from .enhanced_conditional_logic import EnhancedConditionalLogic



class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: ChatOpenAI,
        deep_thinking_llm: ChatOpenAI,
        tool_nodes: Dict[str, ToolNode],
        bull_memory,
        bear_memory,
        trader_memory,
        invest_judge_memory,
        risk_manager_memory,
        conditional_logic: EnhancedConditionalLogic,

    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.risk_manager_memory = risk_manager_memory
        self.conditional_logic = conditional_logic



    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals"]
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "social": Social media analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Create analyst nodes
        analyst_nodes = {}
        delete_nodes = {}

        # FORCE MARKET ANALYST (MANDATORY)
        # It must enable Regime Detection before any other analyst runs.
        # Remove 'market' from selected list to avoid duplication if user selected it.
        # We will add it manually as the first node.
        other_analysts = [a for a in selected_analysts if a != "market"]
        
        # MARKET ANALYST (Always Created)
        analyst_nodes["market"] = create_market_analyst(self.quick_thinking_llm)
        delete_nodes["market"] = create_msg_delete()

        # Loop through other optional analysts (Social, News, Fundamentals)

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["social"] = create_msg_delete()

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["news"] = create_msg_delete()

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["fundamentals"] = create_msg_delete()

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(
            self.quick_thinking_llm, self.bull_memory
        )
        bear_researcher_node = create_bear_researcher(
            self.quick_thinking_llm, self.bear_memory
        )
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.invest_judge_memory
        )
        trader_node = create_trader(self.quick_thinking_llm, self.trader_memory)

        # Create risk analysis nodes
        risky_analyst = create_risky_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        safe_analyst = create_safe_debator(self.quick_thinking_llm)
        risk_manager_node = create_risk_manager(
            self.deep_thinking_llm, self.risk_manager_memory
        )

        # Create workflow
        workflow = StateGraph(AgentState)

        # 0. ADD DATA REGISTRAR (The Foundation)
        workflow.add_node("Data Registrar", create_data_registrar())

        # 1. Add Market Analyst (No Tools, No Loop)
        workflow.add_node("Market Analyst", analyst_nodes["market"])
        # market_analyst_node now returns dict with market_report, regime etc.
        # It does NOT use tools, so no "tools_market" needed.
        
        # We retain "Msg Clear Market" as a bridge node for the Fan-Out if needed,
        # or we just Fan-Out from "Market Analyst" directly.
        # Let's keep it simple: Market Analyst -> Fan Out.

        # 2. Add Other Analysts (SUBGRAPHS)
        # Even though they are tool-less, we keep them as subgraphs or nodes.
        # If they are tool-less, standard nodes are fine, but let's stick to the 
        # existing structure if it works, OR simplify since tool-less = single step.
        # SIMPLIFICATION: If they are tool-less, they are just nodes. 
        # But to avoid breaking the "build_analyst_subgraph" pattern spread elsewhere/logic,
        # we can just add them as regular nodes.
        # Let's add them as Regular Nodes since they are now simple functions.
        
        for analyst_type in other_analysts:
            if analyst_type in analyst_nodes:
                # Direct Node Addition (No Subgraph needed for Tool-less agents)
                workflow.add_node(f"{analyst_type.capitalize()} Analyst", analyst_nodes[analyst_type])

        # Add other nodes
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Risky Analyst", risky_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Safe Analyst", safe_analyst)
        workflow.add_node("Risk Judge", risk_manager_node)

        # Define edges
        
        # 1. START -> Data Registrar
        workflow.add_edge(START, "Data Registrar")
        
        # 2. Data Registrar -> Market Analyst
        workflow.add_edge("Data Registrar", "Market Analyst")
        
        # 3. Market Analyst -> Fan-Out
        # We fan out to [Social, News, Fundamentals]
        
        # Sync Node
        def analyst_sync_node(state: AgentState):
            return {}
        workflow.add_node("Analyst Sync", analyst_sync_node)

        if len(other_analysts) > 0:
            for analyst_type in other_analysts:
                 workflow.add_edge("Market Analyst", f"{analyst_type.capitalize()} Analyst")
                 # And they all go to Sync
                 workflow.add_edge(f"{analyst_type.capitalize()} Analyst", "Analyst Sync")
        else:
            workflow.add_edge("Market Analyst", "Analyst Sync")

        # 4. Sync -> Debate
        workflow.add_edge("Analyst Sync", "Bull Researcher")

        # Add remaining edges (Debate Loop)
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate_with_validation,
            {
                "Bear Researcher": "Bear Researcher",
                "Bull Researcher": "Bull Researcher", 
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate_with_validation,
            {
                "Bull Researcher": "Bull Researcher",
                "Bear Researcher": "Bear Researcher", 
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_edge("Research Manager", "Trader")

        # --- LEGACY RISK ARCHITECTURE (DISABLED FOR PHASE 2) ---
        # The Gatekeeper now assumes final authority immediately after the Trader.
        # The Risk Debate layer will be reintegrated in Phase 3 or refactored to advise the Trader.
        
        # 1. FAN-OUT: Trader -> All 3 Analysts
        # workflow.add_edge("Trader", "Risky Analyst")
        # workflow.add_edge("Trader", "Safe Analyst")
        # workflow.add_edge("Trader", "Neutral Analyst")

        # 2. DEFINE SYNC NODE (The Barrier)
        # def risk_sync_node(state: AgentState):
        #     return {} 
        # workflow.add_node("Risk Sync", risk_sync_node)
        
        # 3. FAN-IN: Analysts -> Sync
        # workflow.add_edge("Risky Analyst", "Risk Sync")
        # workflow.add_edge("Safe Analyst", "Risk Sync")
        # workflow.add_edge("Neutral Analyst", "Risk Sync")

        # 4. SYNC -> JUDGE
        # workflow.add_edge("Risk Sync", "Risk Judge")

        # 5. JUDGE -> END
        # workflow.add_edge("Risk Judge", END)

        # Compile and return
        # --- PHASE 2: EXECUTION GATEKEEPER ---
        from .execution_gatekeeper import create_execution_gatekeeper
        workflow.add_node("Execution Gatekeeper", create_execution_gatekeeper())
        
        # Path: Trader -> Gatekeeper -> END
        workflow.add_edge("Trader", "Execution Gatekeeper")
        workflow.add_edge("Execution Gatekeeper", END)

        # Compile and return
        return workflow.compile()
