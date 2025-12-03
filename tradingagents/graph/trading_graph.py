# TradingAgents/graph/trading_graph.py

import os
from pathlib import Path
import json
from datetime import date
from typing import Dict, Any, Tuple, List, Optional

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.dataflows.config import set_config

# Import tools from new registry-based system
from tradingagents.tools.generator import get_agent_tools

from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config: Dict[str, Any] = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG

        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(
            os.path.join(self.config["project_dir"], "dataflows/data_cache"),
            exist_ok=True,
        )

        # Initialize LLMs
        if self.config["llm_provider"].lower() == "openai" or self.config["llm_provider"] == "ollama" or self.config["llm_provider"] == "openrouter":
            self.deep_thinking_llm = ChatOpenAI(model=self.config["deep_think_llm"], base_url=self.config["backend_url"])
            self.quick_thinking_llm = ChatOpenAI(model=self.config["quick_think_llm"], base_url=self.config["backend_url"])
        elif self.config["llm_provider"].lower() == "anthropic":
            self.deep_thinking_llm = ChatAnthropic(model=self.config["deep_think_llm"], base_url=self.config["backend_url"])
            self.quick_thinking_llm = ChatAnthropic(model=self.config["quick_think_llm"], base_url=self.config["backend_url"])
        elif self.config["llm_provider"].lower() == "google":
            # Explicitly pass Google API key from environment
            google_api_key = os.getenv("GOOGLE_API_KEY")
            if not google_api_key:
                raise ValueError("GOOGLE_API_KEY environment variable not set. Please add it to your .env file.")
            self.deep_thinking_llm = ChatGoogleGenerativeAI(model=self.config["deep_think_llm"], google_api_key=google_api_key)
            self.quick_thinking_llm = ChatGoogleGenerativeAI(model=self.config["quick_think_llm"], google_api_key=google_api_key)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.config['llm_provider']}")
        
        # Initialize memories only if enabled
        if self.config.get("enable_memory", False):
            self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
            self.bear_memory = FinancialSituationMemory("bear_memory", self.config)
            self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
            self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", self.config)
            self.risk_manager_memory = FinancialSituationMemory("risk_manager_memory", self.config)

            # Load historical memories if configured
            if self.config.get("load_historical_memories", False):
                self._load_historical_memories()
        else:
            # Create dummy memory objects that don't use embeddings
            self.bull_memory = None
            self.bear_memory = None
            self.trader_memory = None
            self.invest_judge_memory = None
            self.risk_manager_memory = None

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Initialize components
        self.conditional_logic = ConditionalLogic()
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.bull_memory,
            self.bear_memory,
            self.trader_memory,
            self.invest_judge_memory,
            self.risk_manager_memory,
            self.conditional_logic,
        )

        self.propagator = Propagator()
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph
        self.graph = self.graph_setup.setup_graph(selected_analysts)

    def _load_historical_memories(self):
        """Load pre-built historical memories from disk."""
        import pickle
        import glob

        memory_dir = self.config.get("memory_dir", os.path.join(self.config["data_dir"], "memories"))

        if not os.path.exists(memory_dir):
            print(f"⚠️  Memory directory not found: {memory_dir}")
            print("   Run scripts/build_historical_memories.py to create memories")
            return

        print(f"\n📚 Loading historical memories from {memory_dir}...")

        memory_map = {
            "bull": self.bull_memory,
            "bear": self.bear_memory,
            "trader": self.trader_memory,
            "invest_judge": self.invest_judge_memory,
            "risk_manager": self.risk_manager_memory
        }

        for agent_type, memory in memory_map.items():
            # Find the most recent memory file for this agent type
            pattern = os.path.join(memory_dir, f"{agent_type}_memory_*.pkl")
            files = glob.glob(pattern)

            if not files:
                print(f"   ⚠️  No historical memories found for {agent_type}")
                continue

            # Use the most recent file
            latest_file = max(files, key=os.path.getmtime)

            try:
                with open(latest_file, 'rb') as f:
                    data = pickle.load(f)

                # Add memories to the collection
                if data["documents"] and data["metadatas"] and data["embeddings"]:
                    memory.situation_collection.add(
                        documents=data["documents"],
                        metadatas=data["metadatas"],
                        embeddings=data["embeddings"],
                        ids=data["ids"]
                    )

                    print(f"   ✅ {agent_type}: Loaded {len(data['documents'])} memories from {os.path.basename(latest_file)}")
                else:
                    print(f"   ⚠️  {agent_type}: Empty memory file")

            except Exception as e:
                print(f"   ❌ Error loading {agent_type} memories: {e}")

        print("📚 Historical memory loading complete\n")

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """Create tool nodes for different agents using registry-based system.

        This dynamically reads agent-tool mappings from the registry,
        eliminating the need for hardcoded tool lists.
        """
        tool_nodes = {}

        # Create tool nodes for each agent type
        for agent_name in ["market", "social", "news", "fundamentals"]:
            # Get tools for this agent from the registry
            agent_tools = get_agent_tools(agent_name)

            if agent_tools:
                tool_nodes[agent_name] = ToolNode(agent_tools)
            else:
                # Log warning if no tools found for this agent
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"No tools found for agent '{agent_name}' in registry")

        return tool_nodes

    def propagate(self, company_name, trade_date):
        """Run the trading agents graph for a company on a specific date."""

        self.ticker = company_name

        # Initialize state
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date
        )
        args = self.propagator.get_graph_args()

        if self.debug:
            # Debug mode with tracing
            trace = []
            for chunk in self.graph.stream(init_agent_state, **args):
                if len(chunk["messages"]) == 0:
                    pass
                else:
                    chunk["messages"][-1].pretty_print()
                    trace.append(chunk)

            final_state = trace[-1]
        else:
            # Standard mode without tracing
            final_state = self.graph.invoke(init_agent_state, **args)

        # Store current state for reflection
        self.curr_state = final_state

        # Log state
        self._log_state(trade_date, final_state)

        # Return decision and processed signal
        return final_state, self.process_signal(final_state["final_trade_decision"])

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                "judge_decision": final_state["investment_debate_state"][
                    "judge_decision"
                ],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "risky_history": final_state["risk_debate_state"]["risky_history"],
                "safe_history": final_state["risk_debate_state"]["safe_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }

        # Save to file
        directory = Path(f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/")
        directory.mkdir(parents=True, exist_ok=True)

        with open(
            f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/full_states_log_{trade_date}.json",
            "w",
        ) as f:
            json.dump(self.log_states_dict, f, indent=4)

    def reflect_and_remember(self, returns_losses):
        """Reflect on decisions and update memory based on returns."""
        # Skip reflection if memory is disabled
        if not self.config.get("enable_memory", False):
            return
            
        self.reflector.reflect_bull_researcher(
            self.curr_state, returns_losses, self.bull_memory
        )
        self.reflector.reflect_bear_researcher(
            self.curr_state, returns_losses, self.bear_memory
        )
        self.reflector.reflect_trader(
            self.curr_state, returns_losses, self.trader_memory
        )
        self.reflector.reflect_invest_judge(
            self.curr_state, returns_losses, self.invest_judge_memory
        )
        self.reflector.reflect_risk_manager(
            self.curr_state, returns_losses, self.risk_manager_memory
        )

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)

if __name__ == "__main__":
    # Build the full TradingAgents graph
    tg = TradingAgentsGraph()
    
    print("Generating graph diagrams...")
    
    # Export a PNG diagram (requires Graphviz)
    try:
        # get_graph() returns the drawable graph structure
        tg.graph.get_graph().draw_png("trading_graph.png")
        print("✅ PNG diagram saved as trading_graph.png")
    except Exception as e:
        print(f"⚠️  Could not generate PNG (Graphviz may be missing): {e}")
        
    # Export a Mermaid markdown file for easy embedding in docs/README
    try:
        mermaid_src = tg.graph.get_graph().draw_mermaid()
        with open("trading_graph.mmd", "w") as f:
            f.write(mermaid_src)
        print("✅ Mermaid diagram saved as trading_graph.mmd")
    except Exception as e:
        print(f"⚠️  Could not generate Mermaid diagram: {e}")
