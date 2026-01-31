# TradingAgents/graph/trading_graph.py

import os
import sys
from pathlib import Path
import json
from datetime import date, datetime
from typing import Dict, Any, Tuple, List, Optional

# Add frontend backend to path for database access
FRONTEND_BACKEND_PATH = Path(__file__).parent.parent.parent / "frontend" / "backend"
if str(FRONTEND_BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(FRONTEND_BACKEND_PATH))

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from tradingagents.claude_max_llm import ClaudeMaxLLM

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
    get_global_news
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
            # Use ClaudeMaxLLM to leverage Claude Max subscription via CLI
            self.deep_thinking_llm = ClaudeMaxLLM(model=self.config["deep_think_llm"])
            self.quick_thinking_llm = ClaudeMaxLLM(model=self.config["quick_think_llm"])
        elif self.config["llm_provider"].lower() == "google":
            self.deep_thinking_llm = ChatGoogleGenerativeAI(model=self.config["deep_think_llm"])
            self.quick_thinking_llm = ChatGoogleGenerativeAI(model=self.config["quick_think_llm"])
        else:
            raise ValueError(f"Unsupported LLM provider: {self.config['llm_provider']}")
        
        # Initialize memories
        self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
        self.bear_memory = FinancialSituationMemory("bear_memory", self.config)
        self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
        self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", self.config)
        self.risk_manager_memory = FinancialSituationMemory("risk_manager_memory", self.config)

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

        # Save to frontend database for UI display
        self._save_to_frontend_db(trade_date, final_state)

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

    def _save_to_frontend_db(self, trade_date: str, final_state: Dict[str, Any]):
        """Save pipeline data to the frontend database for UI display.

        Args:
            trade_date: The date of the analysis
            final_state: The final state from the graph execution
        """
        try:
            from database import (
                init_db,
                save_agent_report,
                save_debate_history,
                save_pipeline_steps_bulk,
                save_data_source_logs_bulk
            )

            # Initialize database if needed
            init_db()

            symbol = final_state.get("company_of_interest", self.ticker)
            now = datetime.now().isoformat()

            # 1. Save agent reports
            agent_reports = [
                ("market", final_state.get("market_report", "")),
                ("news", final_state.get("news_report", "")),
                ("social_media", final_state.get("sentiment_report", "")),
                ("fundamentals", final_state.get("fundamentals_report", "")),
            ]

            for agent_type, content in agent_reports:
                if content:
                    save_agent_report(
                        date=trade_date,
                        symbol=symbol,
                        agent_type=agent_type,
                        report_content=content,
                        data_sources_used=[]
                    )

            # 2. Save investment debate
            invest_debate = final_state.get("investment_debate_state", {})
            if invest_debate:
                save_debate_history(
                    date=trade_date,
                    symbol=symbol,
                    debate_type="investment",
                    bull_arguments=invest_debate.get("bull_history", ""),
                    bear_arguments=invest_debate.get("bear_history", ""),
                    judge_decision=invest_debate.get("judge_decision", ""),
                    full_history=invest_debate.get("history", "")
                )

            # 3. Save risk debate
            risk_debate = final_state.get("risk_debate_state", {})
            if risk_debate:
                save_debate_history(
                    date=trade_date,
                    symbol=symbol,
                    debate_type="risk",
                    risky_arguments=risk_debate.get("risky_history", ""),
                    safe_arguments=risk_debate.get("safe_history", ""),
                    neutral_arguments=risk_debate.get("neutral_history", ""),
                    judge_decision=risk_debate.get("judge_decision", ""),
                    full_history=risk_debate.get("history", "")
                )

            # 4. Save pipeline steps (tracking the stages)
            pipeline_steps = [
                {"step_number": 1, "step_name": "initialize", "status": "completed", "started_at": now, "completed_at": now, "output_summary": "Pipeline initialized"},
                {"step_number": 2, "step_name": "market_analysis", "status": "completed", "started_at": now, "completed_at": now, "output_summary": "Market analysis complete" if final_state.get("market_report") else "Skipped"},
                {"step_number": 3, "step_name": "news_analysis", "status": "completed", "started_at": now, "completed_at": now, "output_summary": "News analysis complete" if final_state.get("news_report") else "Skipped"},
                {"step_number": 4, "step_name": "social_analysis", "status": "completed", "started_at": now, "completed_at": now, "output_summary": "Social analysis complete" if final_state.get("sentiment_report") else "Skipped"},
                {"step_number": 5, "step_name": "fundamental_analysis", "status": "completed", "started_at": now, "completed_at": now, "output_summary": "Fundamental analysis complete" if final_state.get("fundamentals_report") else "Skipped"},
                {"step_number": 6, "step_name": "investment_debate", "status": "completed", "started_at": now, "completed_at": now, "output_summary": invest_debate.get("judge_decision", "")[:100] if invest_debate else "Skipped"},
                {"step_number": 7, "step_name": "trader_decision", "status": "completed", "started_at": now, "completed_at": now, "output_summary": final_state.get("trader_investment_plan", "")[:100] if final_state.get("trader_investment_plan") else "Skipped"},
                {"step_number": 8, "step_name": "risk_debate", "status": "completed", "started_at": now, "completed_at": now, "output_summary": risk_debate.get("judge_decision", "")[:100] if risk_debate else "Skipped"},
                {"step_number": 9, "step_name": "final_decision", "status": "completed", "started_at": now, "completed_at": now, "output_summary": final_state.get("final_trade_decision", "")[:100] if final_state.get("final_trade_decision") else "Pending"},
            ]
            save_pipeline_steps_bulk(trade_date, symbol, pipeline_steps)

            print(f"[Frontend DB] Saved pipeline data for {symbol} on {trade_date}")

        except Exception as e:
            print(f"[Frontend DB] Warning: Could not save to frontend database: {e}")
            # Don't fail the main process if frontend DB save fails

    def reflect_and_remember(self, returns_losses):
        """Reflect on decisions and update memory based on returns."""
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
