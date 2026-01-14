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

from .conditional_logic import ConditionalLogic


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
        conditional_logic: ConditionalLogic,
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

    def build_analyst_subgraph(self, analyst_node, delete_node, tool_node, check_condition, name, state_schema):
        """Builder for Analyst Subgraphs (Isolation Sandbox).
        
        Each analyst runs in its own StateGraph to prevent sharing the 'messages' list
        with other parallel analysts.
        
        Flow: START -> Msg Clear (Init) -> Analyst -> [Tools -> Analyst] -> END
        
        Args:
            analyst_node: The main agent function
            delete_node: Function to clear messages (used as init)
            tool_node: The tool execution node
            check_condition: Function to decide loop vs end
            name: Name of the analyst (for logging/labels)
            state_schema: The strictly typed State class for this subgraph
        """
        # USE STRICT SCHEMA HERE instead of AgentState
        subgraph = StateGraph(state_schema)
        
        # Add Nodes
        # We invoke 'delete_node' first to ensure a CLEAN SLATE for this subgraph.
        # This effectively isolates the message history.
        subgraph.add_node("Init_Clear", delete_node)
        subgraph.add_node("Analyst", analyst_node)
        subgraph.add_node("Tools", tool_node)
        
        # Edges
        # 1. START -> Clear (Wipe parent messages to avoid contamination)
        subgraph.add_edge(START, "Init_Clear")
        
        # 2. Clear -> Analyst
        subgraph.add_edge("Init_Clear", "Analyst")
        
        # 3. Analyst -> Conditional
        subgraph.add_conditional_edges(
            "Analyst",
            check_condition,
            {
                # Map the string return values of condition to our internal nodes
                f"tools_{name}": "Tools",     # Map external name to internal "Tools"
                f"Msg Clear {name.capitalize()}": END # Map external finish to END
            }
        )
        
        # 4. Tools -> Analyst
        subgraph.add_edge("Tools", "Analyst")
        
        return subgraph.compile()

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
        tool_nodes = {}

        # FORCE MARKET ANALYST (MANDATORY)
        # It must enable Regime Detection before any other analyst runs.
        # Remove 'market' from selected list to avoid duplication if user selected it.
        # We will add it manually as the first node.
        other_analysts = [a for a in selected_analysts if a != "market"]
        
        # MARKET ANALYST (Always Created)
        analyst_nodes["market"] = create_market_analyst(self.quick_thinking_llm)
        delete_nodes["market"] = create_msg_delete()
        tool_nodes["market"] = self.tool_nodes["market"]

        # Loop through other optional analysts (Social, News, Fundamentals)

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["social"] = create_msg_delete()
            tool_nodes["social"] = self.tool_nodes["social"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["news"] = create_msg_delete()
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["fundamentals"] = create_msg_delete()
            tool_nodes["fundamentals"] = self.tool_nodes["fundamentals"]

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

        # Add analyst nodes to the graph
        # Add analyst nodes to the graph
        # 1. Add Market Analyst (Mandatory)
        workflow.add_node("Market Analyst", analyst_nodes["market"])
        workflow.add_node("Msg Clear Market", delete_nodes["market"])
        workflow.add_node("tools_market", tool_nodes["market"])
        
        # 2. Add Other Analysts (SUBGRAPHS)
        
        # Map analyst types to their Strict State Schemas
        schema_map = {
            "social": SocialAnalystState,
            "news": NewsAnalystState,
            "fundamentals": FundamentalsAnalystState
        }
        
        for analyst_type in other_analysts:
            if analyst_type in analyst_nodes:
                # Build the isolated subgraph for this analyst
                # START -> Clear -> Analyst <-> Tools -> END
                analyst_subgraph = self.build_analyst_subgraph(
                    analyst_node=analyst_nodes[analyst_type],
                    delete_node=delete_nodes[analyst_type],
                    tool_node=tool_nodes[analyst_type],
                    check_condition=getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                    name=analyst_type,
                    state_schema=schema_map.get(analyst_type, AgentState) # Fallback to AgentState if undefined
                )
                
                # Add the SUBGRAPH as a single node to the main workflow
                # The node name is "{Type} Analyst" e.g., "Social Analyst"
                # LangGraph handles the state passing (AgentState -> Subgraph -> AgentState update)
                workflow.add_node(f"{analyst_type.capitalize()} Analyst", analyst_subgraph)

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
        # Define edges
        
        # 1. START -> Market Analyst (Always)
        workflow.add_edge(START, "Market Analyst")
        
        # 2. Market Analyst -> Tools -> Clear
        workflow.add_conditional_edges(
            "Market Analyst",
            self.conditional_logic.should_continue_market,
            ["tools_market", "Msg Clear Market"],
        )
        workflow.add_edge("tools_market", "Market Analyst")
        
        # Compile and return workflow
        
        # --- PARALLEL EXECUTION ARCHITECTURE (FAN-OUT / FAN-IN) ---
        
        # 3. FAN-OUT: Market Analyst -> [Social, News, Fundamentals] (Parallel)
        # Instead of a chain, we connect "Msg Clear Market" to ALL selected analysts.
        if len(other_analysts) > 0:
            for analyst_type in other_analysts:
                 workflow.add_edge("Msg Clear Market", f"{analyst_type.capitalize()} Analyst")
        else:
            # Fallback for simple runs
            workflow.add_edge("Msg Clear Market", "Bull Researcher")

        # 4. PARALLEL BRANCHES & FAN-IN
        # Create Sync Node to wait for all parallel branches
        def analyst_sync_node(state: AgentState):
            return {} # Identity node (Pass-through)
            
        workflow.add_node("Analyst Sync", analyst_sync_node)
        
        for analyst_type in other_analysts:
            # Connect Subgraph output directly to Sync Node
            # The subgraph encapsulates the work and ends at END.
            # In LangGraph, when a node (subgraph) finishes, it transitions to the next edge.
            workflow.add_edge(f"{analyst_type.capitalize()} Analyst", "Analyst Sync")

        # 5. SYNC -> DEBATE
        # Once all parallel branches hit the Sync node, proceed to Bull Researcher
        workflow.add_edge("Analyst Sync", "Bull Researcher")

        # Add remaining edges
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Risky Analyst")
        workflow.add_conditional_edges(
            "Risky Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Safe Analyst": "Safe Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Safe Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Risky Analyst": "Risky Analyst",
                "Risk Judge": "Risk Judge",
            },
        )

        workflow.add_edge("Risk Judge", END)

        # Compile and return
        return workflow.compile()
