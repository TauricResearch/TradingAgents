# TradingAgents/graph/trading_graph.py

import os
from pathlib import Path
import json
from datetime import date
from typing import Dict, Any, Tuple, List, Optional
import time

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
from tradingagents.utils.logging_config import (
    get_logger,
    get_performance_logger,
)

# Import the new abstract tool methods from agent_utils
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_sentiment,
    get_insider_transactions,
    get_global_news,
)

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

        # Initialize logging
        self.logger = get_logger("tradingagents.graph", component="GRAPH")
        self.perf_logger = get_performance_logger()

        self.logger.info(
            "Initializing TradingAgentsGraph",
            extra={
                "context": {
                    "selected_analysts": selected_analysts,
                    "debug": debug,
                    "llm_provider": self.config.get("llm_provider"),
                }
            },
        )

        start_time = time.time()

        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(
            os.path.join(self.config["project_dir"], "dataflows/data_cache"),
            exist_ok=True,
        )

        # Initialize LLMs for chat (using chat model backend)
        self.logger.info(
            f"Initializing chat LLMs with provider: {self.config['llm_provider']}",
            extra={
                "context": {
                    "provider": self.config["llm_provider"],
                    "backend_url": self.config["backend_url"],
                    "deep_model": self.config["deep_think_llm"],
                    "quick_model": self.config["quick_think_llm"],
                }
            },
        )

        if (
            self.config["llm_provider"].lower() == "openai"
            or self.config["llm_provider"] == "ollama"
            or self.config["llm_provider"] == "openrouter"
        ):
            self.deep_thinking_llm = ChatOpenAI(
                model=self.config["deep_think_llm"], base_url=self.config["backend_url"]
            )
            self.quick_thinking_llm = ChatOpenAI(
                model=self.config["quick_think_llm"],
                base_url=self.config["backend_url"],
            )
        elif self.config["llm_provider"].lower() == "anthropic":
            self.deep_thinking_llm = ChatAnthropic(
                model=self.config["deep_think_llm"], base_url=self.config["backend_url"]
            )
            self.quick_thinking_llm = ChatAnthropic(
                model=self.config["quick_think_llm"],
                base_url=self.config["backend_url"],
            )
        elif self.config["llm_provider"].lower() == "google":
            self.deep_thinking_llm = ChatGoogleGenerativeAI(
                model=self.config["deep_think_llm"]
            )
            self.quick_thinking_llm = ChatGoogleGenerativeAI(
                model=self.config["quick_think_llm"]
            )
        else:
            self.logger.error(
                f"Unsupported LLM provider: {self.config['llm_provider']}"
            )
            raise ValueError(f"Unsupported LLM provider: {self.config['llm_provider']}")

        # Initialize embedding configuration (separate from chat LLM)
        # This allows using OpenAI for embeddings while using OpenRouter/other providers for chat
        self._configure_embeddings()

        # Initialize memories (will use separate embedding configuration)
        self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
        self.bear_memory = FinancialSituationMemory("bear_memory", self.config)
        self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
        self.invest_judge_memory = FinancialSituationMemory(
            "invest_judge_memory", self.config
        )
        self.risk_manager_memory = FinancialSituationMemory(
            "risk_manager_memory", self.config
        )

        # Log memory status
        if self.config.get("enable_memory", True):
            self.logger.info(
                f"Memory enabled with provider: {self.config.get('embedding_provider', 'openai')}",
                extra={
                    "context": {
                        "embedding_provider": self.config.get("embedding_provider"),
                        "embedding_model": self.config.get("embedding_model"),
                    }
                },
            )
        else:
            self.logger.warning(
                "Memory disabled - agents will run without historical context"
            )

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

        init_duration = (time.time() - start_time) * 1000
        self.logger.info(
            f"TradingAgentsGraph initialization complete",
            extra={
                "context": {
                    "duration_ms": init_duration,
                    "analysts": selected_analysts,
                    "memory_enabled": self.config.get("enable_memory", True),
                }
            },
        )
        self.perf_logger.log_timing("graph_initialization", init_duration)

    def _configure_embeddings(self):
        """Configure embedding settings, providing smart defaults based on chat LLM provider."""
        # If embedding settings are not explicitly configured, set intelligent defaults
        if "embedding_provider" not in self.config:
            # Default: use OpenAI for embeddings regardless of chat provider
            # This allows using OpenRouter/Anthropic/etc for chat while still having embeddings
            self.config["embedding_provider"] = "openai"

        if "embedding_backend_url" not in self.config:
            # Set backend URL based on embedding provider
            provider = self.config.get("embedding_provider", "openai").lower()
            if provider == "openai":
                self.config["embedding_backend_url"] = "https://api.openai.com/v1"
            elif provider == "ollama":
                self.config["embedding_backend_url"] = "http://localhost:11434/v1"
            else:
                # For unknown providers or "none", use chat backend
                self.config["embedding_backend_url"] = self.config.get(
                    "backend_url", "https://api.openai.com/v1"
                )

        if "embedding_model" not in self.config:
            # Set model based on embedding provider
            provider = self.config.get("embedding_provider", "openai").lower()
            if provider == "ollama":
                self.config["embedding_model"] = "nomic-embed-text"
            elif provider == "openai":
                self.config["embedding_model"] = "text-embedding-3-small"
            else:
                self.config["embedding_model"] = "text-embedding-3-small"

        if "enable_memory" not in self.config:
            # Enable memory by default
            self.config["enable_memory"] = True

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """Create tool nodes for different data sources using abstract methods."""
        return {
            "market": ToolNode(
                [
                    # Core stock data tools
                    get_stock_data,
                    # Technical indicators
                    get_indicators,
                ]
            ),
            "social": ToolNode(
                [
                    # News tools for social media analysis
                    get_news,
                ]
            ),
            "news": ToolNode(
                [
                    # News and insider information
                    get_news,
                    get_global_news,
                    get_insider_sentiment,
                    get_insider_transactions,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    # Fundamental analysis tools
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                ]
            ),
        }

    def propagate(self, company_name, trade_date):
        """Run the trading agents graph for a company on a specific date."""

        self.logger.info(
            f"Starting propagation for {company_name} on {trade_date}",
            extra={
                "context": {
                    "ticker": company_name,
                    "date": str(trade_date),
                }
            },
        )

        start_time = time.time()
        self.ticker = company_name

        # Initialize state
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date
        )
        args = self.propagator.get_graph_args()

        self.logger.debug("Starting graph execution")

        if self.debug:
            # Debug mode with tracing
            self.logger.debug("Running in DEBUG mode with tracing")
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
            self.logger.debug("Running in standard mode")
            final_state = self.graph.invoke(init_agent_state, **args)

        # Store current state for reflection
        self.curr_state = final_state

        # Log state
        self._log_state(trade_date, final_state)

        duration = (time.time() - start_time) * 1000

        decision = self.process_signal(final_state["final_trade_decision"])

        self.logger.info(
            f"Propagation complete for {company_name}",
            extra={
                "context": {
                    "ticker": company_name,
                    "date": str(trade_date),
                    "decision": decision,
                    "duration_ms": duration,
                }
            },
        )

        self.perf_logger.log_timing(
            "propagation",
            duration,
            {"ticker": company_name, "decision": decision},
        )

        # Return decision and processed signal
        return final_state, decision

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        self.logger.debug(f"Logging state for {trade_date}")

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

        log_file = f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/full_states_log_{trade_date}.json"
        with open(log_file, "w") as f:
            json.dump(self.log_states_dict, f, indent=4)

        self.logger.debug(f"State saved to {log_file}")

    def reflect_and_remember(self, returns_losses):
        """Reflect on decisions and update memory based on returns."""
        if not self.config.get("enable_memory", True):
            self.logger.info("Memory disabled - skipping reflection and memory updates")
            return

        self.logger.info(
            f"Starting reflection and memory updates",
            extra={"context": {"returns_losses": returns_losses}},
        )

        start_time = time.time()

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

        duration = (time.time() - start_time) * 1000
        self.logger.info(
            f"Reflection and memory updates complete",
            extra={"context": {"duration_ms": duration}},
        )
        self.perf_logger.log_timing("reflect_and_remember", duration)

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        self.logger.debug("Processing signal")
        decision = self.signal_processor.process_signal(full_signal)
        self.logger.debug(f"Processed signal: {decision}")
        return decision
