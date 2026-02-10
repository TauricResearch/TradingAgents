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

# Import shared logging
from tradingagents.log_utils import add_log, step_timer

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
    get_global_news,
    get_analyst_recommendations,
    get_earnings_data,
    get_institutional_holders,
    get_yfinance_news,
    get_analyst_sentiment,
    get_sector_performance,
    get_earnings_calendar,
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

        # Initialize LLMs with low temperature for deterministic financial analysis
        llm_temp = self.config.get("llm_temperature", 0.2)
        if self.config["llm_provider"].lower() == "openai" or self.config["llm_provider"] == "ollama" or self.config["llm_provider"] == "openrouter":
            self.deep_thinking_llm = ChatOpenAI(model=self.config["deep_think_llm"], base_url=self.config["backend_url"], temperature=llm_temp)
            self.quick_thinking_llm = ChatOpenAI(model=self.config["quick_think_llm"], base_url=self.config["backend_url"], temperature=llm_temp)
        elif self.config["llm_provider"].lower() == "anthropic":
            # Use ClaudeMaxLLM to leverage Claude Max subscription via CLI
            self.deep_thinking_llm = ClaudeMaxLLM(model=self.config["deep_think_llm"], temperature=llm_temp)
            self.quick_thinking_llm = ClaudeMaxLLM(model=self.config["quick_think_llm"], temperature=llm_temp)
        elif self.config["llm_provider"].lower() == "google":
            self.deep_thinking_llm = ChatGoogleGenerativeAI(model=self.config["deep_think_llm"], temperature=llm_temp)
            self.quick_thinking_llm = ChatGoogleGenerativeAI(model=self.config["quick_think_llm"], temperature=llm_temp)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.config['llm_provider']}")
        
        # Initialize memories with graceful error handling for ChromaDB race conditions
        try:
            self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
            self.bear_memory = FinancialSituationMemory("bear_memory", self.config)
            self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
            self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", self.config)
            self.risk_manager_memory = FinancialSituationMemory("risk_manager_memory", self.config)
        except Exception as e:
            # ChromaDB can fail with race conditions in parallel execution
            # Fall back to None memories - agents will work without memory-based recommendations
            add_log("warning", "system", f"ChromaDB memory initialization failed: {str(e)[:100]}. Continuing without memory.")
            self.bull_memory = None
            self.bear_memory = None
            self.trader_memory = None
            self.invest_judge_memory = None
            self.risk_manager_memory = None

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Initialize components
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config.get("max_debate_rounds", 1),
            max_risk_discuss_rounds=self.config.get("max_risk_discuss_rounds", 1),
        )
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
                    # Technical indicators (18 indicators available)
                    get_indicators,
                ]
            ),
            "social": ToolNode(
                [
                    # Sentiment and market perception tools
                    get_yfinance_news,
                    get_analyst_sentiment,
                    get_sector_performance,
                ]
            ),
            "news": ToolNode(
                [
                    # News, insider information, and upcoming catalysts
                    get_news,
                    get_global_news,
                    get_insider_sentiment,
                    get_insider_transactions,
                    get_earnings_calendar,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    # Fundamental analysis tools
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                    get_analyst_recommendations,
                    get_earnings_data,
                    get_institutional_holders,
                ]
            ),
        }

    def propagate(self, company_name, trade_date):
        """Run the trading agents graph for a company on a specific date."""
        import time as _time

        self.ticker = company_name
        pipeline_start = _time.time()
        step_timer.clear()  # Reset per-agent timings for this run
        add_log("info", "system", f"🚀 Starting analysis for {company_name} on {trade_date}")

        # Initialize state
        add_log("info", "system", "Initializing agent state...")
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date
        )
        args = self.propagator.get_graph_args()

        if self.debug:
            # Debug mode with tracing
            add_log("info", "system", "Running in debug mode with tracing...")
            trace = []
            for chunk in self.graph.stream(init_agent_state, **args):
                if len(chunk["messages"]) == 0:
                    pass
                else:
                    chunk["messages"][-1].pretty_print()
                    trace.append(chunk)

            final_state = trace[-1]
        else:
            # Standard mode - log key stages
            add_log("info", "system", f"Running full analysis pipeline for {company_name} (deep={self.config.get('deep_think_llm','?')}, quick={self.config.get('quick_think_llm','?')})...")
            add_log("info", "system", "Pipeline: Data Fetch → Analysts → Bull/Bear Debate → Trader → Risk Debate → Final Decision")

            # Run the full graph (all agents log their own timing)
            graph_start = _time.time()
            final_state = self.graph.invoke(init_agent_state, **args)
            graph_elapsed = _time.time() - graph_start
            add_log("info", "system", f"Graph execution completed in {graph_elapsed:.1f}s")

            # Log completions with report sizes
            if final_state.get("market_report"):
                add_log("success", "market_analyst", f"✅ Market report: {len(final_state['market_report'])} chars")
            if final_state.get("news_report"):
                add_log("success", "news_analyst", f"✅ News report: {len(final_state['news_report'])} chars")
            if final_state.get("sentiment_report"):
                add_log("success", "social_analyst", f"✅ Sentiment report: {len(final_state['sentiment_report'])} chars")
            if final_state.get("fundamentals_report"):
                add_log("success", "fundamentals", f"✅ Fundamentals report: {len(final_state['fundamentals_report'])} chars")

            # Log debate results
            invest_debate = final_state.get("investment_debate_state", {})
            if invest_debate.get("judge_decision"):
                add_log("success", "debate", f"✅ Investment debate decided: {invest_debate['judge_decision'][:100]}...")
            if final_state.get("trader_investment_plan"):
                add_log("success", "trader", f"✅ Trader plan: {final_state['trader_investment_plan'][:100]}...")
            risk_debate = final_state.get("risk_debate_state", {})
            if risk_debate.get("judge_decision"):
                add_log("success", "risk_manager", f"✅ Risk decision: {risk_debate['judge_decision'][:100]}...")

        # Store current state for reflection
        self.curr_state = final_state
        add_log("info", "system", "Storing analysis results...")

        # Log state
        self._log_state(trade_date, final_state)

        # Save to frontend database for UI display
        add_log("info", "system", "Saving pipeline data to database...")
        t0 = _time.time()
        self._save_to_frontend_db(trade_date, final_state)
        add_log("info", "system", f"Database save completed in {_time.time() - t0:.1f}s")

        # Extract and log the final decision + hold_days + confidence + risk
        signal_result = self.process_signal(final_state["final_trade_decision"])
        final_decision = signal_result["decision"]
        hold_days = signal_result.get("hold_days")
        confidence = signal_result.get("confidence", "MEDIUM")
        risk = signal_result.get("risk", "MEDIUM")
        total_elapsed = _time.time() - pipeline_start
        hold_info = f", hold {hold_days}d" if hold_days else ""
        add_log("success", "system", f"✅ Analysis complete for {company_name}: {final_decision}{hold_info}, confidence={confidence}, risk={risk} (total: {total_elapsed:.0f}s)")

        # Return decision, hold_days, confidence, risk
        return final_state, final_decision, hold_days, confidence, risk

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

            # 4. Save pipeline steps — 12 granular steps with per-agent timing
            step_timings = step_timer.get_steps()

            # Define the 12 steps with their IDs, names, and fallback output summaries
            step_defs = [
                (1, "market_analyst", "market_analysis", final_state.get("market_report", "")[:200]),
                (2, "social_media_analyst", "social_analysis", final_state.get("sentiment_report", "")[:200]),
                (3, "news_analyst", "news_analysis", final_state.get("news_report", "")[:200]),
                (4, "fundamentals_analyst", "fundamental_analysis", final_state.get("fundamentals_report", "")[:200]),
                (5, "bull_researcher", "bull_research", invest_debate.get("bull_history", "")[:200]),
                (6, "bear_researcher", "bear_research", invest_debate.get("bear_history", "")[:200]),
                (7, "research_manager", "research_manager", invest_debate.get("judge_decision", "")[:200]),
                (8, "trader", "trader_decision", final_state.get("trader_investment_plan", "")[:200]),
                (9, "aggressive_analyst", "aggressive_analysis", risk_debate.get("risky_history", "")[:200]),
                (10, "conservative_analyst", "conservative_analysis", risk_debate.get("safe_history", "")[:200]),
                (11, "neutral_analyst", "neutral_analysis", risk_debate.get("neutral_history", "")[:200]),
                (12, "risk_manager", "risk_manager", risk_debate.get("judge_decision", "")[:200]),
            ]

            pipeline_steps = []
            for step_num, timer_id, step_name, fallback_summary in step_defs:
                timing = step_timings.get(timer_id, {})
                # Force status to "completed" — we only reach this save code
                # after the graph has fully executed, so all steps must be done.
                # The step_timer may show "running" if end_step() wasn't called
                # due to an exception in the agent.
                pipeline_steps.append({
                    "step_number": step_num,
                    "step_name": step_name,
                    "status": "completed",
                    "started_at": timing.get("started_at", now),
                    "completed_at": timing.get("completed_at", now),
                    "duration_ms": timing.get("duration_ms"),
                    "output_summary": timing.get("output_summary") or fallback_summary or "Completed",
                    "step_details": timing.get("details"),
                })
            # 5. Save raw data source logs from the data fetch store
            from tradingagents.log_utils import raw_data_store

            METHOD_TO_SOURCE = {
                "get_stock_data": ("market_data", "Yahoo Finance"),
                "get_YFin_data": ("market_data", "Yahoo Finance"),
                "get_stock_stats": ("indicators", "Technical Indicators"),
                "get_stock_stats_indicators": ("indicators", "Technical Indicators"),
                "get_fundamentals": ("fundamentals", "Financial Data"),
                "get_balance_sheet": ("fundamentals", "Balance Sheet"),
                "get_income_statement": ("fundamentals", "Income Statement"),
                "get_cashflow": ("fundamentals", "Cash Flow"),
                "get_analyst_recommendations": ("fundamentals", "Analyst Recommendations"),
                "get_earnings_data": ("fundamentals", "Earnings Data"),
                "get_institutional_holders": ("fundamentals", "Institutional Holders"),
                "get_news": ("news", "Google News"),
                "get_global_news": ("news", "Global News"),
                "get_earnings_calendar": ("news", "Earnings Calendar"),
                "get_reddit_posts": ("social_media", "Reddit"),
                "get_yfinance_news": ("social_media", "Yahoo Finance News"),
                "get_analyst_sentiment": ("social_media", "Analyst Sentiment"),
                "get_sector_performance": ("social_media", "Sector Performance"),
            }

            raw_entries = raw_data_store.get_entries()

            # Enrich pipeline step tool_calls with result_preview from raw data
            if raw_entries:
                for step in pipeline_steps:
                    details = step.get("step_details")
                    if details and details.get("tool_calls"):
                        for tc in details["tool_calls"]:
                            for entry in raw_entries:
                                if entry["method"] == tc.get("name"):
                                    tc["result_preview"] = str(entry["raw_data"])[:500]
                                    break

            save_pipeline_steps_bulk(trade_date, symbol, pipeline_steps)

            if raw_entries:
                data_source_logs = []
                for entry in raw_entries:
                    source_type, source_name = METHOD_TO_SOURCE.get(
                        entry["method"], ("other", entry["method"])
                    )
                    data_source_logs.append({
                        "source_type": source_type,
                        "source_name": source_name,
                        "method": entry["method"],
                        "args": entry.get("args", ""),
                        "data_fetched": entry["raw_data"],
                        "fetch_timestamp": entry["timestamp"],
                        "success": True,
                        "error_message": None,
                    })
                save_data_source_logs_bulk(trade_date, symbol, data_source_logs)
                raw_data_store.clear()

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
