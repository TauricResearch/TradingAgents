"""Thin wrapper around TradingAgentsGraph. Frontend never imports the engine."""

from __future__ import annotations

import logging
from collections.abc import Callable
from copy import deepcopy
from datetime import date
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.analyst_execution import (
    AnalystWallTimeTracker,
    build_analyst_execution_plan,
    get_initial_analyst_node,
    sync_analyst_tracker_from_chunk,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph

from backend.integrations.normalize import ANALYST_KEYS, REPORT_TO_AGENT, normalize_final_state

logger = logging.getLogger(__name__)

DEPTH_ROUNDS = {"shallow": 1, "medium": 2, "deep": 3}

EventCallback = Callable[[str, dict[str, Any]], None]


class TradingAgentsAdapter:
    def build_config(
        self,
        *,
        llm_provider: str | None,
        model: str | None,
        quick_model: str | None,
        research_depth: str,
        debate_rounds: int | None,
        temperature: float | None,
        output_language: str = "English",
    ) -> dict[str, Any]:
        config = deepcopy(DEFAULT_CONFIG)
        if llm_provider:
            config["llm_provider"] = llm_provider.lower()
        if model:
            config["deep_think_llm"] = model
        if quick_model:
            config["quick_think_llm"] = quick_model
        elif model:
            config["quick_think_llm"] = model
        rounds = debate_rounds or DEPTH_ROUNDS.get(research_depth, 2)
        config["max_debate_rounds"] = rounds
        config["max_risk_discuss_rounds"] = rounds
        if temperature is not None:
            config["temperature"] = temperature
        config["output_language"] = output_language
        return config

    def run_analysis(
        self,
        *,
        symbol: str,
        analysis_date: str | None,
        selected_analysts: list[str],
        config: dict[str, Any],
        emit: EventCallback,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        trade_date = analysis_date or date.today().isoformat()
        analysts = [key for key in ("market", "social", "news", "fundamentals") if key in selected_analysts]
        if not analysts:
            analysts = ["market"]
        plan = build_analyst_execution_plan(analysts)
        tracker = AnalystWallTimeTracker(plan)
        graph = TradingAgentsGraph(selected_analysts=tuple(analysts), debug=False, config=config)

        emit("analysis_started", {"symbol": symbol, "analysis_date": trade_date})
        first = get_initial_analyst_node(plan)
        emit("agent_started", {"agent_name": first})

        instrument_context = graph.resolve_instrument_context(symbol, "stock")
        init_state = graph.propagator.create_initial_state(
            symbol,
            trade_date,
            asset_type="stock",
            instrument_context=instrument_context,
        )
        args = graph.propagator.get_graph_args()
        trace: list[dict[str, Any]] = []
        completed_reports: set[str] = set()
        debate_started = False
        risk_started = False
        decision_started = False

        for chunk in graph.graph.stream(init_state, **args):
            if should_cancel and should_cancel():
                emit("analysis_failed", {"error": "cancelled"})
                raise RuntimeError("cancelled")
            sync_analyst_tracker_from_chunk(tracker, chunk)
            self._emit_analyst_progress(chunk, completed_reports, emit)
            if chunk.get("investment_debate_state"):
                debate = chunk["investment_debate_state"]
                if not debate_started and (debate.get("bull_history") or debate.get("bear_history")):
                    debate_started = True
                    emit("research_started", {})
                    emit("agent_started", {"agent_name": "Bull Researcher"})
                if debate.get("bull_history"):
                    emit("agent_completed", {"agent_name": "Bull Researcher", "summary": debate.get("bull_history")})
                    emit("agent_started", {"agent_name": "Bear Researcher"})
                if debate.get("bear_history"):
                    emit("agent_completed", {"agent_name": "Bear Researcher", "summary": debate.get("bear_history")})
                    emit("agent_started", {"agent_name": "Research Manager"})
                if debate.get("judge_decision"):
                    emit("agent_completed", {"agent_name": "Research Manager", "summary": debate.get("judge_decision")})
                    emit("research_completed", {})
                    emit("agent_started", {"agent_name": "Trader"})
            if chunk.get("trader_investment_plan"):
                emit("agent_completed", {"agent_name": "Trader", "summary": chunk["trader_investment_plan"]})
                if not risk_started:
                    risk_started = True
                    emit("risk_started", {})
                    emit("agent_started", {"agent_name": "Aggressive Analyst"})
            if chunk.get("risk_debate_state"):
                risk = chunk["risk_debate_state"]
                if risk.get("aggressive_history"):
                    emit("agent_completed", {"agent_name": "Aggressive Analyst", "summary": risk["aggressive_history"]})
                    emit("agent_started", {"agent_name": "Neutral Analyst"})
                if risk.get("neutral_history"):
                    emit("agent_completed", {"agent_name": "Neutral Analyst", "summary": risk["neutral_history"]})
                    emit("agent_started", {"agent_name": "Conservative Analyst"})
                if risk.get("conservative_history"):
                    emit("agent_completed", {"agent_name": "Conservative Analyst", "summary": risk["conservative_history"]})
                if risk.get("judge_decision"):
                    if not decision_started:
                        decision_started = True
                        emit("decision_started", {})
                        emit("agent_started", {"agent_name": "Portfolio Manager"})
                    emit("agent_completed", {"agent_name": "Portfolio Manager", "summary": risk["judge_decision"]})
            trace.append(chunk)

        final_state: dict[str, Any] = {}
        for chunk in trace:
            final_state.update(chunk)
        processed = graph.process_signal(final_state.get("final_trade_decision") or "")
        graph.curr_state = final_state
        graph.ticker = symbol
        try:
            graph.save_reports(final_state, symbol)
        except Exception:
            logger.exception("Failed to persist TradingAgents report tree")
        normalized = normalize_final_state(symbol, final_state, processed)
        emit("analysis_completed", {"decision": normalized.get("action"), "rating": normalized.get("rating")})
        return normalized

    def _emit_analyst_progress(
        self,
        chunk: dict[str, Any],
        completed_reports: set[str],
        emit: EventCallback,
    ) -> None:
        key_to_report = {
            "market": "market_report",
            "social": "sentiment_report",
            "news": "news_report",
            "fundamentals": "fundamentals_report",
        }
        for report_key, agent_name in REPORT_TO_AGENT.items():
            content = chunk.get(report_key)
            if content and report_key not in completed_reports:
                completed_reports.add(report_key)
                emit("agent_completed", {"agent_name": agent_name, "summary": content})
                for key in ("market", "social", "news", "fundamentals"):
                    mapped = key_to_report[key]
                    if mapped not in completed_reports:
                        emit("agent_started", {"agent_name": ANALYST_KEYS[key]})
                        break
