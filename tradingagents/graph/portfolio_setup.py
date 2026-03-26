"""Portfolio Manager workflow graph setup.

Fan-out/fan-in workflow:
  START → load_portfolio → compute_risk → review_holdings
        → prioritize_candidates → macro_summary (parallel)
                                → micro_summary  (parallel)
        → make_pm_decision → execute_trades → END

Non-LLM nodes (load_portfolio, compute_risk, prioritize_candidates,
execute_trades) receive ``repo`` and ``config`` via closure.
LLM nodes (review_holdings, macro_summary, micro_summary, pm_decision)
are created externally and passed in.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from tradingagents.portfolio.candidate_prioritizer import prioritize_candidates
from tradingagents.portfolio.portfolio_states import PortfolioManagerState
from tradingagents.portfolio.risk_evaluator import compute_portfolio_risk
from tradingagents.portfolio.trade_executor import TradeExecutor

logger = logging.getLogger(__name__)

# Default Portfolio dict for safe fallback when portfolio_data is empty or malformed
_EMPTY_PORTFOLIO_DICT = {
    "portfolio_id": "",
    "name": "",
    "cash": 0.0,
    "initial_cash": 0.0,
}


class PortfolioGraphSetup:
    """Builds the Portfolio Manager workflow graph with parallel summary fan-out.

    Args:
        agents: Dict with keys ``review_holdings``, ``macro_summary``,
                ``micro_summary``, and ``pm_decision`` mapping to LLM agent
                node functions.
        repo: PortfolioRepository instance (injected into closure nodes).
        config: Portfolio config dict.
        macro_memory: MacroMemory instance forwarded to summary agents.
        micro_memory: ReflexionMemory instance forwarded to summary agents.
    """

    def __init__(
        self,
        agents: dict[str, Any],
        repo=None,
        config: dict[str, Any] | None = None,
        macro_memory=None,
        micro_memory=None,
    ) -> None:
        self.agents = agents
        self._repo = repo
        self._config = config or {}
        # Memory instances are already baked into the agent closures at the call site
        # (portfolio_graph.py passes them to create_macro/micro_summary_agent).
        # Stored here for future direct access by non-LLM closure nodes if needed.
        self._macro_memory = macro_memory
        self._micro_memory = micro_memory

    # ------------------------------------------------------------------
    # Node factories (non-LLM)
    # ------------------------------------------------------------------

    def _make_load_portfolio_node(self):
        repo = self._repo
        config = self._config

        def load_portfolio_node(state):
            portfolio_id = state["portfolio_id"]
            prices = state.get("prices") or {}
            try:
                if repo is None:
                    from tradingagents.portfolio.repository import PortfolioRepository
                    _repo = PortfolioRepository(config=config)
                else:
                    _repo = repo
                portfolio, holdings = _repo.get_portfolio_with_holdings(
                    portfolio_id, prices
                )
                data = {
                    "portfolio": portfolio.to_dict(),
                    "holdings": [h.to_dict() for h in holdings],
                }
            except Exception as exc:
                logger.error("load_portfolio_node: %s", exc)
                data = {"portfolio": {}, "holdings": [], "error": str(exc)}
            return {
                "portfolio_data": json.dumps(data),
                "sender": "load_portfolio",
            }

        return load_portfolio_node

    def _make_compute_risk_node(self):
        def compute_risk_node(state):
            portfolio_data_str = state.get("portfolio_data") or "{}"
            prices = state.get("prices") or {}
            try:
                portfolio_data = json.loads(portfolio_data_str)
                from tradingagents.portfolio.models import Holding, Portfolio

                portfolio = Portfolio.from_dict(portfolio_data.get("portfolio") or _EMPTY_PORTFOLIO_DICT)
                holdings = [
                    Holding.from_dict(h) for h in (portfolio_data.get("holdings") or [])
                ]

                # Enrich holdings with prices so current_value is populated
                if prices and portfolio.total_value is None:
                    equity = sum(prices.get(h.ticker, 0.0) * h.shares for h in holdings)
                    total_value = portfolio.cash + equity
                    for h in holdings:
                        if h.ticker in prices:
                            h.enrich(prices[h.ticker], total_value)
                    portfolio.enrich(holdings)

                # Build simple price histories from single-point prices
                # (real usage would pass historical prices via scan_summary or state)
                price_histories: dict[str, list[float]] = {}
                scan_summary = state.get("scan_summary") or {}
                for h in holdings:
                    history = scan_summary.get("price_histories", {}).get(h.ticker)
                    if history:
                        price_histories[h.ticker] = history
                    elif h.ticker in prices:
                        # Single-point price — returns will be empty, metrics None
                        price_histories[h.ticker] = [prices[h.ticker]]

                metrics = compute_portfolio_risk(portfolio, holdings, price_histories)
            except Exception as exc:
                logger.error("compute_risk_node: %s", exc)
                metrics = {"error": str(exc)}
            return {
                "risk_metrics": json.dumps(metrics),
                "sender": "compute_risk",
            }

        return compute_risk_node

    def _make_prioritize_candidates_node(self):
        config = self._config

        def prioritize_candidates_node(state):
            portfolio_data_str = state.get("portfolio_data") or "{}"
            scan_summary = state.get("scan_summary") or {}
            try:
                portfolio_data = json.loads(portfolio_data_str)
                from tradingagents.portfolio.models import Holding, Portfolio

                portfolio = Portfolio.from_dict(portfolio_data.get("portfolio") or _EMPTY_PORTFOLIO_DICT)
                holdings = [
                    Holding.from_dict(h) for h in (portfolio_data.get("holdings") or [])
                ]
                candidates = scan_summary.get("stocks_to_investigate") or []
                prices = state.get("prices") or {}
                if prices:
                    equity = sum(prices.get(h.ticker, 0.0) * h.shares for h in holdings)
                    total_value = portfolio.cash + equity
                    for h in holdings:
                        if h.ticker in prices:
                            h.enrich(prices[h.ticker], total_value)
                    portfolio.enrich(holdings)

                from tradingagents.portfolio.memory_loader import build_selection_memory

                try:
                    selection_memory = build_selection_memory()
                except Exception as exc:
                    logger.warning("prioritize_candidates_node: could not load selection_memory: %s", exc)
                    selection_memory = None

                ranked = prioritize_candidates(candidates, portfolio, holdings, config, selection_memory=selection_memory)
            except Exception as exc:
                logger.error("prioritize_candidates_node: %s", exc)
                ranked = []
            return {
                "prioritized_candidates": json.dumps(ranked),
                "sender": "prioritize_candidates",
            }

        return prioritize_candidates_node

    def _make_execute_trades_node(self):
        repo = self._repo
        config = self._config

        def execute_trades_node(state):
            portfolio_id = state["portfolio_id"]
            analysis_date = state.get("analysis_date") or ""
            prices = state.get("prices") or {}
            pm_decision_str = state.get("pm_decision") or "{}"
            try:
                decisions = json.loads(pm_decision_str)
            except (json.JSONDecodeError, TypeError):
                decisions = {}

            try:
                if repo is None:
                    from tradingagents.portfolio.repository import PortfolioRepository
                    _repo = PortfolioRepository(config=config)
                else:
                    _repo = repo
                executor = TradeExecutor(repo=_repo, config=config)
                result = executor.execute_decisions(
                    portfolio_id, decisions, prices, date=analysis_date
                )
            except Exception as exc:
                logger.error("execute_trades_node: %s", exc)
                result = {"error": str(exc), "executed_trades": [], "failed_trades": []}
            return {
                "execution_result": json.dumps(result),
                "sender": "execute_trades",
            }

        return execute_trades_node

    # ------------------------------------------------------------------
    # Graph assembly
    # ------------------------------------------------------------------

    def setup_graph(self):
        """Build and compile the portfolio workflow graph with parallel summary fan-out.

        Topology:
            START → load_portfolio → compute_risk → review_holdings
                  → prioritize_candidates → macro_summary (parallel)
                                          → micro_summary  (parallel)
                  → make_pm_decision → execute_trades → END

        Returns:
            A compiled LangGraph graph ready to invoke.
        """
        workflow = StateGraph(PortfolioManagerState)

        # Register non-LLM nodes
        workflow.add_node("load_portfolio", self._make_load_portfolio_node())
        workflow.add_node("compute_risk", self._make_compute_risk_node())
        workflow.add_node("prioritize_candidates", self._make_prioritize_candidates_node())
        workflow.add_node("execute_trades", self._make_execute_trades_node())

        # Register LLM nodes
        workflow.add_node("review_holdings", self.agents["review_holdings"])
        workflow.add_node("macro_summary", self.agents["macro_summary"])
        workflow.add_node("micro_summary", self.agents["micro_summary"])
        workflow.add_node("make_pm_decision", self.agents["pm_decision"])

        # Sequential backbone
        workflow.add_edge(START, "load_portfolio")
        workflow.add_edge("load_portfolio", "compute_risk")
        workflow.add_edge("compute_risk", "review_holdings")
        workflow.add_edge("review_holdings", "prioritize_candidates")

        # Fan-out: prioritize_candidates → both summary nodes (parallel)
        workflow.add_edge("prioritize_candidates", "macro_summary")
        workflow.add_edge("prioritize_candidates", "micro_summary")

        # Fan-in: both summary nodes → make_pm_decision
        workflow.add_edge("macro_summary", "make_pm_decision")
        workflow.add_edge("micro_summary", "make_pm_decision")

        # Tail
        workflow.add_edge("make_pm_decision", "execute_trades")
        workflow.add_edge("execute_trades", END)

        return workflow.compile()
