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
from datetime import datetime
from tradingagents.utils.logger import override_logger as logger


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

from .enhanced_conditional_logic import EnhancedConditionalLogic
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
            self.deep_thinking_llm = ChatGoogleGenerativeAI(
                model=self.config["deep_think_llm"],
                base_url=self.config["backend_url"], 
                max_retries=10,
                request_timeout=60
            )
            self.quick_thinking_llm = ChatGoogleGenerativeAI(
                model=self.config["quick_think_llm"],
                max_retries=10,
                base_url=self.config["backend_url"],
                request_timeout=60
            )
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
        self.conditional_logic = EnhancedConditionalLogic()


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
                ],
                handle_tool_errors=True,
            ),
            "social": ToolNode(
                [
                    # News tools for social media analysis
                    get_news,
                ],
                handle_tool_errors=True,
            ),
            "news": ToolNode(
                [
                    # News and insider information
                    get_news,
                    get_global_news,
                    get_insider_sentiment,
                    get_insider_transactions,
                ],
                handle_tool_errors=True,
            ),
            "fundamentals": ToolNode(
                [
                    # Fundamental analysis tools
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                ],
                handle_tool_errors=True,
            ),
        }

    def reset_memory(self):
        """Clear all agent memories to prevent context bleeding between runs."""
        self.bull_memory.clear()
        self.bear_memory.clear()
        self.trader_memory.clear()
        self.invest_judge_memory.clear()
        self.risk_manager_memory.clear()

    def propagate(self, company_name, trade_date):
        """Run the trading agents graph for a company on a specific date."""
        # 1. FIX MEMORY LEAK
        self.reset_memory()

        self.ticker = company_name
        
        # 3. Register real company name for anonymization
        try:
            from tradingagents.utils.anonymizer import TickerAnonymizer
            import yfinance as yf
            anonymizer = TickerAnonymizer()
            ticker_obj = yf.Ticker(company_name)
            info = ticker_obj.info
            full_name = info.get("longName") or info.get("shortName")
            if full_name:
                # print(f"DEBUG: Registering company name for {company_name}: {full_name}")
                anonymizer.set_company_name(company_name, full_name)
        except Exception as e:
            # print(f"DEBUG: Failed to fetch company name for {company_name}: {e}")
            pass

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
        
        # 🟢 INSTITUTIONAL AUTHORIZATION (Phase 2.5)
        # The ExecutionGatekeeper is now the final node in the graph.
        # It's output is stored in state["final_trade_decision"].
        auth_decision = final_state.get("final_trade_decision")
        
        if not auth_decision:
             logger.error("🔥 GRAPH CRITICAL: Final decision missing from state!")
             return final_state, {"action": "HOLD", "quantity": 0, "reason": "Graph Failure"}

        status = auth_decision.get("status")
        action = auth_decision.get("action", "HOLD")
        
        logger.info(f"🛡️ GATEKEEPER RESULT: {status} -> {action}")
        
        # Process the signal for the execution engine
        processed_signal = {
            "action": action,
            "quantity": 0, # Quantity logic moves to Phase 4
            "reason": f"[{status}] {auth_decision.get('details', {}).get('reason', '')}"
        }

        # Handle formatting for compatibility
        if processed_signal["action"] == "NO_OP":
             processed_signal["action"] = "HOLD"

        return final_state, processed_signal

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            # 2. FIX BLIND SPOT: Log the Math
            "market_regime": final_state.get("market_regime", "UNKNOWN"), 
            "regime_metrics": final_state.get("regime_metrics", {}),
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
            "trader_investment_decision": final_state.get("trader_investment_plan", "N/A"),
            "risk_debate_state": {
                "risky_history": final_state.get("risk_debate_state", {}).get("risky_history", []),
                "safe_history": final_state.get("risk_debate_state", {}).get("safe_history", []),
                "neutral_history": final_state.get("risk_debate_state", {}).get("neutral_history", []),
                "history": final_state.get("risk_debate_state", {}).get("history", []),
                "judge_decision": final_state.get("risk_debate_state", {}).get("judge_decision", "N/A"),
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
        # OPTIMIZATION: Replaced 5 calls with 1 Batch Call
        
        memories = {
            "bull": self.bull_memory,
            "bear": self.bear_memory,
            "trader": self.trader_memory,
            "judge": self.invest_judge_memory,
            "risk": self.risk_manager_memory
        }
        
        self.reflector.reflect_on_full_session(
            self.curr_state, returns_losses, memories
        )

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        # Handle dict if signal was overridden, otherwise handle string from LLM
        if isinstance(full_signal, dict):
            return {
                "action": full_signal.get("action", "HOLD"),
                "quantity": full_signal.get("quantity", 0),
                "reason": full_signal.get("reasoning", "OVERRIDDEN")
            }
        return self.signal_processor.process_signal(full_signal)

        sma_200 = hard_data["sma_200"]
        sma_50 = hard_data.get("sma_50", 0.0)
        growth = hard_data["revenue_growth"]
        
        # 0. Insider Veto (Rule B: Insider Selling > $50M + Downtrend)
        is_downtrend_50 = price < sma_50
        if insider_flow < -50_000_000 and is_downtrend_50:
            if "BUY" in trade_decision_str.upper():
                 logger.warning(f"🛑 INSIDER VETO TRIGGERED for {self.ticker}")
                 logger.warning(f"   Reason: Insiders sold ${abs(insider_flow):,.0f} (> $50M) and Price < 50SMA.")
                 return {
                    "action": "HOLD",
                    "quantity": 0,
                    "reasoning": f"INSIDER VETO: Blocked BUY. Insiders sold ${abs(insider_flow):,.0f} into a downtrend (< 50SMA).",
                    "confidence": 1.0
                }
        
        # 1. Technical Uptrend (Price > 200 SMA)
        is_technical_uptrend = price > sma_200

        # EMERGENCY BYPASS FOR DEBUGGING
        if regime_val == "UNKNOWN" and is_technical_uptrend:
             logger.warning("⚠️ DEBUG OVERRIDE: Forcing Regime to 'TRENDING_UP' because Price > SMA")
             # is_bull_regime will be True below by default
        
        # 2. Hyper-Growth (> 30% YoY)
        is_hyper_growth = growth > 0.30
        
        # 3. Supportive Regime (Protect leaders unless it's a clear TRENDING_DOWN regime)
        # Note: If regime is 'VOLATILE' or 'UNKNOWN', is_bear_regime is False -> Override Logic ACTIVATES.
        is_bear_regime = regime_val in ["TRENDING_DOWN", "BEAR", "BEARISH"]
        is_bull_regime = not is_bear_regime
        
        msg_override = f"DEBUG OVERRIDE: Price={price}, SMA={sma_200}, Growth={growth}, Regime='{regime_val}'"
        logger.info(msg_override)
        
        # ⚠️ EMERGENCY DIAGNOSTIC
        logger.info(f"DEBUG CHECK: Technical (Price > SMA) = {is_technical_uptrend}")
        logger.info(f"DEBUG CHECK: Growth (> 30%) = {is_hyper_growth}")
        logger.info(f"DEBUG CHECK: Bull Regime (Not Down) = {is_bull_regime}")
        
        logger.info(f"DEBUG CHECK: Technical={is_technical_uptrend}, Growth={is_hyper_growth}, BullRegime={is_bull_regime}")

        # 4. Trigger Override if trying to SELL a leader in a bull market
        if is_technical_uptrend and is_hyper_growth and is_bull_regime:
            # We check if the decision string contains SELL or STRONG_SELL
            decision_upper = trade_decision_str.upper()
            if "SELL" in decision_upper:
                allowed_action = "HOLD"
                reasoning = (
                        f"OVERRIDE: System attempted to short a Hyper-Growth stock ({growth:.1%}) "
                        f"above its 200-day trend (${sma_200:.2f}) in a Bull regime. "
                        f"Original Decision: {trade_decision_str[:100]}..."
                    )
                
                logger.warning(f"🛑 TREND OVERRIDE TRIGGERED for {self.ticker}")
                logger.warning(f"   Reason: Stock (${price:.2f}) is > 200SMA (${sma_200:.2f}) and Growth is {growth:.1%}")
                logger.warning(f"   Action 'SELL' blocked. Converting to '{allowed_action}'.")
                
                return {
                    "action": allowed_action,
                    "quantity": 0,
                    "reasoning": reasoning,
                    "confidence": 1.0
                }
            else:
                 logger.info("DEBUG OVERRIDE: Conditions met, but decision was NOT 'SELL'. No action needed.")
        else:
            logger.info("DEBUG OVERRIDE: Conditions NOT met. Passive.")

        return trade_decision_str
