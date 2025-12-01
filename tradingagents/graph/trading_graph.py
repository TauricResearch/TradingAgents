# TradingAgents/graph/trading_graph.py

import os
import json
import logging
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Dict, Any, Tuple, List, Optional, TYPE_CHECKING

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.managers.orchestrator import create_portfolio_orchestrator
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.dataflows.config import set_config
from tradingagents.integrations.alpaca_mcp import AlpacaMCPClient, AlpacaMCPConfig, AlpacaMCPError
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.graph.scheduler import create_action_scheduler

if TYPE_CHECKING:
    from tradingagents.services.account import AccountSnapshot

def _extract_json_block(text: str) -> Dict[str, Any]:
    """Attempt to locate a JSON object within free-form text."""

    import json
    if not text:
        return {}

    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        for part in parts:
            candidate = part.strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                try:
                    return json.loads(candidate)
                except Exception:
                    continue
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except Exception:
            return {}
    return {}

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
        *,
        skip_initial_probes: bool = False,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.logger = logging.getLogger(__name__)

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
            self.deep_thinking_llm = ChatGoogleGenerativeAI(model=self.config["deep_think_llm"])
            self.quick_thinking_llm = ChatGoogleGenerativeAI(model=self.config["quick_think_llm"])
        else:
            raise ValueError(f"Unsupported LLM provider: {self.config['llm_provider']}")

        # Portfolio + Alpaca configuration
        self.portfolio_profile: Dict[str, Any] = self.config.get("portfolio_orchestrator", {})
        try:
            self.alpaca_config = AlpacaMCPConfig.from_dict(self.config.get("alpaca_mcp", {}))
            self.alpaca_config.validate()
        except ValueError as exc:
            self.logger.warning("Alpaca MCP configuration invalid: %s", exc)
            self.alpaca_config = AlpacaMCPConfig.from_dict(
                {
                    "enabled": False,
                    "transport": "http",
                    "host": "127.0.0.1",
                    "port": 8000,
                    "command": "",
                    "timeout_seconds": 30.0,
                    "required_tools": [],
                }
            )
        self._alpaca_client: Optional[AlpacaMCPClient] = None
        self._manual_portfolio_snapshot: Optional[Dict[str, str]] = None

        self.trade_execution_config: Dict[str, Any] = self.config.get("trade_execution", {})

        # Probe MCP connectivity early so any configuration issues are visible
        # before the graph starts processing signals.
        if not skip_initial_probes:
            self._report_mcp_connectivity()
            self._log_alpaca_account_overview()

        # Initialize memories
        self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
        self.bear_memory = FinancialSituationMemory("bear_memory", self.config)
        self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
        self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", self.config)
        self.risk_manager_memory = FinancialSituationMemory("risk_manager_memory", self.config)

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        orchestrator_node = create_portfolio_orchestrator(
            self.quick_thinking_llm,
            self.portfolio_profile,
            self._collect_portfolio_context,
            self._fetch_quick_signals,
            self._generate_plan_with_llm,
        )
        action_scheduler_node = create_action_scheduler()

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
            orchestrator_node,
            action_scheduler_node,
        )

        self.propagator = Propagator()
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.trade_date = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph
        self.graph = self.graph_setup.setup_graph(selected_analysts)

    # ------------------------------------------------------------------
    # Portfolio context helpers
    # ------------------------------------------------------------------
    def _report_mcp_connectivity(self) -> None:
        if getattr(self.alpaca_config, "enabled", False):
            client = self._get_alpaca_client()
            if client and not client.verify_connection():
                self.logger.warning(
                    "Alpaca MCP connection check failed; see previous log messages for details."
                )
        else:
            self.logger.info("Alpaca MCP disabled; skipping connectivity check.")

    def _get_alpaca_client(self) -> Optional[AlpacaMCPClient]:
        if not getattr(self.alpaca_config, "enabled", False):
            return None
        if self._alpaca_client is None:
            self._alpaca_client = AlpacaMCPClient(self.alpaca_config, self.logger)
        return self._alpaca_client

    def _log_alpaca_account_overview(self) -> None:
        if not getattr(self.alpaca_config, "enabled", False):
            msg = "Alpaca MCP disabled; skipping account overview."
            self.logger.info(msg)
            print(msg)
            return

        client = self._get_alpaca_client()
        if client is None:
            return

        try:
            account_text = (client.fetch_account_info() or "").strip()
            positions_text = (client.fetch_positions() or "").strip()
            orders_text = (client.fetch_orders() or "").strip()
        except AlpacaMCPError as exc:
            msg = f"Unable to retrieve Alpaca account overview: {exc}"
            self.logger.warning(msg)
            print(f"WARNING: {msg}")
            return
        except Exception as exc:  # pragma: no cover - defensive logging
            msg = f"Unexpected error while fetching Alpaca account overview: {exc}"
            self.logger.warning(msg)
            print(f"WARNING: {msg}")
            return

        overview_lines = [
            "Alpaca account overview:",
            account_text or "<no account data>",
            "",
            "Open positions:",
            positions_text or "<no open positions>",
            "",
            "Recent orders:",
            orders_text or "<no recent orders>",
        ]
        overview_message = "\n".join(overview_lines)
        self.logger.info(overview_message)
        print(overview_message)

    def set_manual_portfolio_snapshot(self, snapshot: "AccountSnapshot") -> None:
        """Provide a pre-fetched Alpaca snapshot to reuse during orchestration."""
        self._manual_portfolio_snapshot = {
            "account": snapshot.account_text,
            "positions": snapshot.positions_text,
            "orders": snapshot.orders_text,
        }

    def clear_manual_portfolio_snapshot(self) -> None:
        """Clear any cached snapshot so subsequent runs fetch live data."""
        self._manual_portfolio_snapshot = None

    def _collect_portfolio_context(self, symbols: List[str]) -> List[Dict[str, str]]:
        symbols = symbols or []
        if self._manual_portfolio_snapshot:
            cached = self._manual_portfolio_snapshot
            snapshots: List[Dict[str, str]] = []
            for idx, symbol in enumerate(symbols):
                snapshots.append(
                    {
                        "symbol": symbol.upper(),
                        "status": "alpaca_cached",
                        "account": cached.get("account", "") if idx == 0 else "",
                        "positions": cached.get("positions", "") if idx == 0 else "",
                        "orders": cached.get("orders", "") if idx == 0 else "",
                        "summary_prompt": "Cached Alpaca snapshot" if idx == 0 else "",
                    }
                )
            return snapshots

        client = self._get_alpaca_client()
        if client is None:
            return [
                {
                    "symbol": symbol.upper(),
                    "status": "alpaca_disabled",
                    "account": "",
                    "positions": "",
                    "orders": "",
                    "summary_prompt": "Alpaca MCP disabled; using static portfolio profile only.",
                }
                for symbol in symbols
            ]

        try:
            account_text = client.fetch_account_info()
            positions_text = client.fetch_positions()
            orders_text = client.fetch_orders()
            snapshots: List[Dict[str, str]] = []
            for idx, symbol in enumerate(symbols):
                snapshots.append(
                    {
                        "symbol": symbol.upper(),
                        "status": "alpaca_connected",
                        "account": account_text if idx == 0 else "",
                        "positions": positions_text if idx == 0 else "",
                        "orders": orders_text if idx == 0 else "",
                        "summary_prompt": "Live Alpaca data available" if idx == 0 else "",
                    }
                )
            return snapshots
        except AlpacaMCPError as exc:
            self.logger.warning("Alpaca MCP call failed: %s", exc)
            return [
                {
                    "symbol": symbol.upper(),
                    "status": f"alpaca_error: {exc}",
                    "account": "" if idx else "",
                    "positions": "",
                    "orders": "",
                    "summary_prompt": "Unable to fetch Alpaca context." if idx == 0 else "",
                }
                for idx, symbol in enumerate(symbols)
            ]
        except Exception as exc:  # pragma: no cover
            self.logger.error("Unexpected Alpaca MCP failure: %s", exc)
            return [
                {
                    "symbol": symbol.upper(),
                    "status": "alpaca_error",
                    "account": "",
                    "positions": "",
                    "orders": "",
                    "summary_prompt": "Unexpected error while fetching Alpaca context." if idx == 0 else "",
                }
                for idx, symbol in enumerate(symbols)
            ]

    def _fetch_quick_signals(self, symbol: str, trade_date: str, lookback_days: int, limit: int) -> Dict[str, str]:
        if not trade_date:
            trade_date = date.today().isoformat()

        try:
            trade_dt = datetime.fromisoformat(trade_date)
        except ValueError:
            try:
                trade_dt = datetime.fromisoformat(f"{trade_date}T00:00:00")
            except Exception:
                trade_dt = datetime.today()

        trade_date_value = trade_dt.date()
        start_dt = trade_date_value - timedelta(days=lookback_days)

        def safe_call(method: str, *args) -> str:
            try:
                return str(route_to_vendor(method, *args))
            except Exception as exc:  # pragma: no cover
                self.logger.debug("Quick signal fetch failed for %s: %s", symbol, exc)
                return f"Failed to fetch {method}: {exc}"

        news_text = safe_call("get_news", symbol, start_dt.isoformat(), trade_date_value.isoformat())
        global_text = safe_call("get_global_news", trade_date_value.isoformat(), lookback_days, limit)

        def truncate(txt: str, max_chars: int = 2000) -> str:
            if len(txt) <= max_chars:
                return txt
            return txt[: max_chars - 3] + "..."

        return {
            "symbol": symbol.upper(),
            "news": truncate(news_text, 1500),
            "global": truncate(global_text, 1500),
        }

    def check_market_status(self) -> Dict[str, Any]:
        """Return the current Alpaca market clock status if available."""
        client = self._get_alpaca_client()
        if client is None:
            return {"is_open": True, "reason": "alpaca_disabled"}
        try:
            clock_text = client.fetch_market_clock()
        except AlpacaMCPError as exc:
            self.logger.warning("Unable to fetch market clock: %s", exc)
            return {"is_open": False, "reason": f"clock_error: {exc}"}
        except Exception as exc:  # pragma: no cover
            self.logger.warning("Unexpected market clock error: %s", exc)
            return {"is_open": True, "reason": "clock_unavailable"}

        normalized = clock_text.lower()
        is_open = "is open: yes" in normalized
        parsed = self._parse_market_clock(clock_text)
        return {
            "is_open": is_open,
            "clock_text": clock_text,
            **parsed,
        }

    def _parse_market_clock(self, clock_text: str) -> Dict[str, str]:
        current_time = None
        next_open = None
        next_close = None
        for line in clock_text.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            label, value = line.split(":", 1)
            label = label.strip().lower()
            value = value.strip()
            if label == "current time":
                current_time = value
            elif label == "next open":
                next_open = value
            elif label == "next close":
                next_close = value
        payload: Dict[str, str] = {}
        if current_time:
            payload["current_time"] = current_time
        if next_open:
            payload["next_open"] = next_open
        if next_close:
            payload["next_close"] = next_close
        return payload

    def _generate_plan_with_llm(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt = (
            "You are the sequential planning engine for TradingAgents. "
            "Given the payload (account_summary, positions_summary, hypotheses, quick_signals, market_data, trade_policy), "
            "recommend the next sequence of analysts/managers to involve and the immediate directive for the hypothesis. "
            "Always reply with JSON containing: actions (array of role identifiers), next_decision (monitor|escalate|trade|execute), "
            "notes (string), reasoning (array of short bullet explanations)."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload)},
        ]

        try:
            response = self.quick_thinking_llm.invoke(messages)
            content = getattr(response, "content", None)
            if isinstance(content, list):
                content = "".join(
                    chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
                    for chunk in content
                )
            if not content:
                content = str(response)
        except Exception as exc:  # pragma: no cover
            self.logger.warning("Sequential plan generation failed: %s", exc)
            return {"error": str(exc)}

        structured: Dict[str, Any]
        try:
            structured = json.loads(content)
        except json.JSONDecodeError:
            structured = _extract_json_block(content)

        if not isinstance(structured, dict):
            structured = {}

        actions = structured.get("actions")
        if not isinstance(actions, list):
            actions = [str(actions)] if actions else []

        reasoning = structured.get("reasoning")
        if not isinstance(reasoning, list):
            reasoning = [str(reasoning)] if reasoning else []

        plan = {
            "actions": [str(item).strip().lower() for item in actions if str(item).strip()],
            "next_decision": str(structured.get("next_decision") or "monitor").lower(),
            "notes": str(structured.get("notes") or ""),
            "reasoning": [str(item) for item in reasoning if str(item)],
        }

        return {
            "structured": plan,
            "text": content,
        }


    def _maybe_execute_trade(
        self,
        final_state: Dict[str, Any],
        decision_text: str,
        *,
        quantity: Optional[float] = None,
        notional: Optional[float] = None,
        reference_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        exec_cfg = self.trade_execution_config or {}
        if not exec_cfg.get("enabled"):
            return {"status": "disabled", "reason": "trade_execution_disabled"}

        action = self._extract_action(decision_text)
        symbol = final_state.get("company_of_interest", "")
        if not symbol:
            return {"status": "skipped", "reason": "missing_symbol"}

        if action not in {"BUY", "SELL"}:
            return {"status": "skipped", "reason": f"action_{action}"}

        def _as_quantity(value: Any) -> Optional[float]:
            try:
                qty = float(value)
            except (TypeError, ValueError):
                return None
            return qty if qty > 0 else None

        resolved_qty = _as_quantity(quantity)

        ref_price_value = _as_quantity(reference_price)
        if not ref_price_value and isinstance(final_state, dict):
            ref_price_value = _as_quantity(final_state.get("reference_price"))

        if resolved_qty is None and notional not in (None, ""):
            try:
                notional_value = float(notional)
            except (TypeError, ValueError):
                notional_value = None
            if notional_value and ref_price_value:
                computed = int(notional_value // ref_price_value)
                resolved_qty = float(computed) if computed > 0 else None

        if resolved_qty is None:
            resolved_qty = _as_quantity(exec_cfg.get("default_order_quantity", 0))

        if not ref_price_value and resolved_qty and ref_price_value is None:
            # Best effort: try to recover reference price from hypothesis/trader notes if present
            ref_price_value = _as_quantity(final_state.get("reference_price")) if isinstance(final_state, dict) else None

        # Guard against exceeding buying power if price is available
        if resolved_qty and ref_price_value:
            try:
                client = self._get_alpaca_client()
                if client:
                    account_text = client.fetch_account_info()
                    buying_power = self._parse_buying_power(account_text)
                    estimated_cost = resolved_qty * ref_price_value
                    if buying_power and estimated_cost > buying_power:
                        capped = int(buying_power // ref_price_value)
                        if capped <= 0:
                            return {
                                "status": "skipped",
                                "reason": "insufficient_buying_power",
                                "buying_power": buying_power,
                                "requested_qty": resolved_qty,
                                "reference_price": ref_price_value,
                            }
                        resolved_qty = float(capped)
            except Exception:
                # Fail open on guard; order placement will still respect dry_run flag
                pass

        if resolved_qty is None or resolved_qty <= 0:
            return {"status": "skipped", "reason": "invalid_quantity"}

        client = self._get_alpaca_client()
        if client is None:
            return {"status": "failed", "reason": "alpaca_disabled"}

        payload = {
            "symbol": symbol,
            "side": "buy" if action == "BUY" else "sell",
            "order_type": "market",
            "time_in_force": exec_cfg.get("time_in_force", "day").upper(),
            "quantity": float(resolved_qty),
        }

        try:
            clock_text = client.fetch_market_clock()
            if "Is Open: Yes" not in clock_text:
                return {"status": "market_closed", "payload": payload, "clock": clock_text}
        except AlpacaMCPError as exc:
            self.logger.warning("Unable to fetch market clock: %s", exc)
        except Exception as exc:  # pragma: no cover
            self.logger.warning("Unexpected market clock error: %s", exc)

        if exec_cfg.get("dry_run", True):
            self.logger.info("[DRY RUN] Would submit Alpaca order: %s", payload)
            return {"status": "dry_run", "payload": payload}

        try:
            response_text = client.place_stock_order(payload)
            self.logger.info("Alpaca MCP order submitted: %s", response_text)
            return {
                "status": "executed",
                "payload": payload,
                "response": response_text,
            }
        except AlpacaMCPError as exc:
            self.logger.error("Order submission failed: %s", exc)
            return {"status": "failed", "reason": str(exc), "payload": payload}
        except Exception as exc:  # pragma: no cover
            self.logger.exception("Unexpected error during order submission")
            return {"status": "failed", "reason": str(exc), "payload": payload}

    def _parse_buying_power(self, account_text: str) -> float:
        for line in account_text.splitlines():
            if "buying power" not in line.lower():
                continue
            parts = line.split(":", 1)
            if len(parts) != 2:
                continue
            value = parts[1].strip().replace("$", "").replace(",", "")
            try:
                return float(value)
            except ValueError:
                continue
        return 0.0

    def _extract_action(self, decision_text: str) -> str:
        if not decision_text:
            return "UNKNOWN"
        normalized = decision_text.upper()
        if "FINAL TRANSACTION PROPOSAL" in normalized:
            if "**BUY**" in normalized:
                return "BUY"
            if "**SELL**" in normalized:
                return "SELL"
            if "**HOLD**" in normalized:
                return "HOLD"

        for keyword in ("BUY", "SELL", "HOLD"):
            if keyword in normalized:
                return keyword
        if "TRADE" in normalized:
            return "BUY"
        return "UNKNOWN"

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

    def propagate(self, company_name=None, trade_date=None, *, initial_overrides: Optional[Dict[str, Any]] = None):
        """Run the trading agents graph for a company on a specific date."""

        company_value = (company_name or "").strip()
        trade_date_value = str(trade_date) if trade_date else date.today().isoformat()

        self.ticker = company_value or "portfolio"
        self.trade_date = trade_date_value

        # Initialize state
        init_agent_state = self.propagator.create_initial_state(
            company_value, trade_date_value
        )
        if initial_overrides:
            init_agent_state.update(initial_overrides)
        init_agent_state["portfolio_profile"] = self.portfolio_profile
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
        preferred_ticker = final_state.get("target_ticker") or final_state.get("company_of_interest")
        if preferred_ticker:
            self.ticker = preferred_ticker

        # Log state
        self._log_state(trade_date, final_state)

        # Return decision and processed signal
        decision_text = final_state.get("final_trade_decision", "")
        if not decision_text:
            orchestrator_action = str(final_state.get("orchestrator_action") or "").strip()
            if orchestrator_action:
                decision_text = orchestrator_action.upper()
                final_state["final_trade_decision"] = decision_text
        if decision_text:
            processed_decision = self.process_signal(decision_text)
        else:
            processed_decision = ""
        execution_result = self._maybe_execute_trade(final_state, decision_text)
        processed_result = {
            "decision": processed_decision,
            "execution": execution_result,
        }
        final_state["execution_result"] = execution_result
        self._write_run_summary(final_state, processed_result)
        return final_state, processed_result

    def execute_trade_directive(
        self,
        symbol: str,
        action: str,
        *,
        quantity: Optional[float] = None,
        notional: Optional[float] = None,
        reference_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Execute a trade directive issued outside the standard graph run."""
        directive = (action or "").strip().upper()
        minimal_state = {"company_of_interest": symbol}
        return self._maybe_execute_trade(
            minimal_state,
            directive,
            quantity=quantity,
            notional=notional,
            reference_price=reference_price,
        )

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        ticker_for_logs = final_state.get("target_ticker") or final_state.get("company_of_interest") or "portfolio"
        invest_state = final_state.get("investment_debate_state") or {}
        risk_state = final_state.get("risk_debate_state") or {}
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state.get("company_of_interest"),
            "target_ticker": final_state.get("target_ticker"),
            "trade_date": final_state.get("trade_date"),
            "market_report": final_state.get("market_report", ""),
            "sentiment_report": final_state.get("sentiment_report", ""),
            "news_report": final_state.get("news_report", ""),
            "fundamentals_report": final_state.get("fundamentals_report", ""),
            "investment_debate_state": {
                "bull_history": invest_state.get("bull_history", ""),
                "bear_history": invest_state.get("bear_history", ""),
                "history": invest_state.get("history", ""),
                "current_response": invest_state.get("current_response", ""),
                "judge_decision": invest_state.get("judge_decision", ""),
                "count": invest_state.get("count", 0),
            },
            "trader_investment_decision": final_state.get("trader_investment_plan", ""),
            "risk_debate_state": {
                "risky_history": risk_state.get("risky_history", ""),
                "safe_history": risk_state.get("safe_history", ""),
                "neutral_history": risk_state.get("neutral_history", ""),
                "history": risk_state.get("history", ""),
                "judge_decision": risk_state.get("judge_decision", ""),
                "latest_speaker": risk_state.get("latest_speaker", ""),
                "count": risk_state.get("count", 0),
            },
            "investment_plan": final_state.get("investment_plan", ""),
            "final_trade_decision": final_state.get("final_trade_decision", ""),
            "portfolio_summary": final_state.get("portfolio_summary"),
            "orchestrator_status": final_state.get("orchestrator_status"),
            "alpaca_account_text": final_state.get("alpaca_account_text"),
            "alpaca_positions_text": final_state.get("alpaca_positions_text"),
            "alpaca_orders_text": final_state.get("alpaca_orders_text"),
            "execution_result": final_state.get("execution_result"),
            "orchestrator_hypotheses": final_state.get("orchestrator_hypotheses", []),
            "active_hypothesis": final_state.get("active_hypothesis"),
            "orchestrator_focus_symbols": final_state.get("orchestrator_focus_symbols", []),
            "orchestrator_quick_signals": final_state.get("orchestrator_quick_signals", {}),
            "orchestrator_market_data": final_state.get("orchestrator_market_data", {}),
            "orchestrator_ticker_plans": final_state.get("orchestrator_ticker_plans", {}),
            "orchestrator_pending_tickers": final_state.get("orchestrator_pending_tickers", []),
            "orchestrator_buying_power": final_state.get("orchestrator_buying_power"),
            "orchestrator_cash_available": final_state.get("orchestrator_cash_available"),
            "orchestrator_portfolio_value": final_state.get("orchestrator_portfolio_value"),
            "scheduled_analysts_plan": final_state.get("scheduled_analysts_plan", []),
            "orchestrator_action": final_state.get("orchestrator_action"),
            "action_queue": final_state.get("action_queue", []),
            "next_directive": final_state.get("next_directive"),
            "planner_plan": final_state.get("planner_plan", {}),
            "planner_notes": final_state.get("planner_notes", ""),
        }

        # Save to file
        directory = Path(f"eval_results/{ticker_for_logs}/TradingAgentsStrategy_logs/")
        directory.mkdir(parents=True, exist_ok=True)

        with open(
            f"eval_results/{ticker_for_logs}/TradingAgentsStrategy_logs/full_states_log_{trade_date}.json",
            "w",
        ) as f:
            json.dump(self.log_states_dict, f, indent=4, default=str)

    def _write_run_summary(self, final_state: Dict[str, Any], processed: Dict[str, Any]) -> None:
        try:
            results_dir = Path(self.config.get("results_dir", "./results"))
        except Exception:
            results_dir = Path("./results")
        try:
            results_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            ticker_for_summary = final_state.get("target_ticker") or self.ticker or "portfolio"
            summary_path = results_dir / f"run_{ticker_for_summary}_{timestamp}.json"
            summary = {
                "ticker": final_state.get("target_ticker"),
                "trade_date": final_state.get("trade_date"),
                "orchestrator_summary": final_state.get("portfolio_summary"),
                "orchestrator_status": final_state.get("orchestrator_status"),
                "orchestrator_action": final_state.get("orchestrator_action"),
                "orchestrator_hypotheses": final_state.get("orchestrator_hypotheses"),
                "orchestrator_focus_symbols": final_state.get("orchestrator_focus_symbols"),
                "orchestrator_quick_signals": final_state.get("orchestrator_quick_signals"),
                "orchestrator_market_data": final_state.get("orchestrator_market_data"),
                "orchestrator_ticker_plans": final_state.get("orchestrator_ticker_plans"),
                "orchestrator_pending_tickers": final_state.get("orchestrator_pending_tickers"),
                "orchestrator_buying_power": final_state.get("orchestrator_buying_power"),
                "orchestrator_cash_available": final_state.get("orchestrator_cash_available"),
                "orchestrator_portfolio_value": final_state.get("orchestrator_portfolio_value"),
                "active_hypothesis": final_state.get("active_hypothesis"),
                "scheduled_analysts_plan": final_state.get("scheduled_analysts_plan"),
                "action_queue": final_state.get("action_queue"),
                "next_directive": final_state.get("next_directive"),
                "planner_plan": final_state.get("planner_plan"),
                "planner_notes": final_state.get("planner_notes"),
                "execution": processed.get("execution"),
                "decision": processed.get("decision"),
            }
            with open(summary_path, "w", encoding="utf-8") as handle:
                json.dump(summary, handle, indent=2, default=str)
            try:
                print("[Run Summary] Final decision:", summary.get("decision"))
                print("[Run Summary] Execution status:", summary.get("execution"))
            except Exception:
                pass
        except Exception as exc:  # pragma: no cover
            self.logger.warning("Failed to write run summary: %s", exc)

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
