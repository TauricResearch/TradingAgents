"""Framework-neutral streamed analysis service."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from time import sleep
from typing import Any, Protocol

from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.fund_data_tools import use_preloaded_fund_snapshot
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.analyst_execution import build_analyst_execution_plan
from tradingagents.graph.checkpointer import (
    clear_checkpoint,
    get_checkpointer,
    has_checkpoint,
    thread_id,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.usage import BudgetExhaustedError

Emit = Callable[[str, dict[str, Any]], None]


class AnalysisCancelledError(Exception):
    pass


class AnalysisService(Protocol):
    def execute(
        self,
        request: dict[str, Any],
        emit: Emit,
        should_cancel: Callable[[], bool],
    ) -> dict[str, Any]: ...


REPORT_KEYS = {
    "market_report": "Market Analysis",
    "sentiment_report": "Sentiment Analysis",
    "news_report": "News Analysis",
    "fundamentals_report": "Fund Analysis",
    "investment_plan": "Research Decision",
    "trader_investment_plan": "Trading Plan",
    "final_trade_decision": "Final Decision",
}


def checkpoint_signature(request: dict[str, Any]) -> str:
    return "|".join([
        "analysts=" + ",".join(request["analysts"]),
        f"debate={request['research_depth']}",
        f"risk={request['research_depth']}",
        f"asset={request['asset_type']}",
    ])


def has_valid_checkpoint(request: dict[str, Any]) -> bool:
    if not DEFAULT_CONFIG.get("checkpoint_enabled"):
        return False
    return has_checkpoint(
        DEFAULT_CONFIG["data_cache_dir"],
        request["symbol"],
        str(request["analysis_date"]),
        checkpoint_signature(request),
    )


def discard_checkpoint(request: dict[str, Any]) -> None:
    if DEFAULT_CONFIG.get("checkpoint_enabled"):
        clear_checkpoint(
            DEFAULT_CONFIG["data_cache_dir"],
            request["symbol"],
            str(request["analysis_date"]),
            checkpoint_signature(request),
        )


class GraphAnalysisService:
    """Own graph setup and turn streamed LangGraph states into typed events."""

    def execute(self, request: dict[str, Any], emit: Emit, should_cancel: Callable[[], bool]) -> dict[str, Any]:
        snapshot = request.get("_fund_snapshot")
        with use_preloaded_fund_snapshot(snapshot if isinstance(snapshot, dict) else None):
            result = self._execute(request, emit, should_cancel)
        if isinstance(snapshot, dict) and not result.get("fund_snapshot"):
            result["fund_snapshot"] = deepcopy(snapshot)
        return result

    def _execute(self, request: dict[str, Any], emit: Emit, should_cancel: Callable[[], bool]) -> dict[str, Any]:
        config = deepcopy(DEFAULT_CONFIG)
        config.update(
            llm_provider=request["llm_provider"],
            quick_think_llm=request["quick_model"],
            deep_think_llm=request["deep_model"],
            output_language=request["output_language"],
            max_debate_rounds=request["research_depth"],
            max_risk_discuss_rounds=request["research_depth"],
            benchmark_ticker=request.get("benchmark_symbol"),
            llm_max_retries=0,
        )
        graph = TradingAgentsGraph(selected_analysts=request["analysts"], config=config)
        symbol = request["symbol"]
        asset_type = request["asset_type"]
        identity = request.get("_instrument_identity")
        context = (
            build_instrument_context(symbol, asset_type, identity)
            if isinstance(identity, dict)
            else graph.resolve_instrument_context(symbol, asset_type)
        )
        initial = graph.propagator.create_initial_state(
            symbol,
            request["analysis_date"],
            asset_type=asset_type,
            instrument_context=context,
            benchmark_symbol=request.get("benchmark_symbol") or graph._resolve_benchmark(symbol),
        )
        args = graph.propagator.get_graph_args()
        checkpoint_context = None
        if config.get("checkpoint_enabled"):
            signature = checkpoint_signature(request)
            if not request.get("_resume_checkpoint"):
                clear_checkpoint(
                    config["data_cache_dir"], symbol, str(request["analysis_date"]), signature
                )
            checkpoint_context = get_checkpointer(config["data_cache_dir"], symbol)
            saver = checkpoint_context.__enter__()
            graph.graph = graph.workflow.compile(checkpointer=saver)
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = thread_id(
                symbol, str(request["analysis_date"]), signature
            )
        plan = build_analyst_execution_plan(request["analysts"])
        emitted_reports: dict[str, str] = {}
        completed_agents: set[str] = set()
        emit("analysis.started", {"symbol": symbol, "asset_type": asset_type})
        for spec in plan.specs:
            emit("agent.started", {"agent": spec.agent_node})

        final_state = initial
        completed = False
        try:
            for chunk in graph.graph.stream(initial, **args):
                if should_cancel():
                    raise AnalysisCancelledError
                final_state = chunk
                for spec in plan.specs:
                    value = chunk.get(spec.report_key)
                    if value and emitted_reports.get(spec.report_key) != value:
                        emitted_reports[spec.report_key] = value
                        emit("report.updated", {"section": spec.report_key, "title": REPORT_KEYS[spec.report_key], "content": value})
                        if spec.agent_node not in completed_agents:
                            completed_agents.add(spec.agent_node)
                            emit("agent.completed", {"agent": spec.agent_node})
            completed = True
        except AnalysisCancelledError:
            raise
        except BudgetExhaustedError as exc:
            raise BudgetExhaustedError(exc.reason, partial_result=final_state) from exc
        finally:
            if completed and config.get("checkpoint_enabled"):
                clear_checkpoint(
                    config["data_cache_dir"], symbol, str(request["analysis_date"]),
                    checkpoint_signature(request),
                )
            if checkpoint_context is not None:
                checkpoint_context.__exit__(None, None, None)
        return final_state


@dataclass
class DemoAnalysisService:
    """Deterministic local service for UI development and Playwright."""

    delay: float = 0.03

    def execute(self, request: dict[str, Any], emit: Emit, should_cancel: Callable[[], bool]) -> dict[str, Any]:
        symbol = request["symbol"]
        asset_type = request["asset_type"]
        emit("analysis.started", {"symbol": symbol, "asset_type": asset_type})
        if symbol == "FAIL":
            raise RuntimeError("Provider is temporarily unavailable")
        reports = {
            "market_report": "Price remains above its medium-term trend with measured volatility.",
            "sentiment_report": "News and market sentiment are balanced with no extreme signal.",
            "news_report": "Macro conditions remain the primary near-term catalyst.",
            "fundamentals_report": (
                "## Fund Analysis\n\nThe fund offers broad, liquid exposure. Latest holdings metadata "
                "is not historical point-in-time data. Expense ratio and concentration should be monitored."
                if asset_type == "fund"
                else "## Fundamentals Analysis\n\nOperating quality and valuation remain central to the thesis."
            ),
        }
        agents = ["Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst"]
        result: dict[str, Any] = {
            "company_of_interest": symbol,
            "asset_type": asset_type,
            "trade_date": request["analysis_date"],
            "benchmark_symbol": request.get("benchmark_symbol") or "SPY",
        }
        event_delay = 0.3 if symbol == "SLOW" else self.delay
        for agent, (key, content) in zip(agents, reports.items(), strict=True):
            if key.removesuffix("_report") not in request["analysts"] and key != "sentiment_report":
                emit("agent.skipped", {"agent": agent})
                continue
            if should_cancel():
                raise AnalysisCancelledError
            emit("agent.started", {"agent": agent})
            sleep(event_delay)
            result[key] = content
            emit("report.updated", {"section": key, "title": REPORT_KEYS[key], "content": content})
            emit("agent.completed", {"agent": agent})
        if should_cancel():
            raise AnalysisCancelledError
        result.update(
            investment_plan="**Rating: Overweight**\n\nThe evidence supports measured exposure.",
            trader_investment_plan="Accumulate gradually with explicit risk limits.",
            final_trade_decision="**Final Rating: Overweight**\n\nMaintain disciplined position sizing.",
            fund_snapshot=_demo_snapshot(symbol, asset_type, request["analysis_date"]),
            generated_at=datetime.now(UTC).isoformat(),
        )
        for key in ("investment_plan", "trader_investment_plan", "final_trade_decision"):
            emit("report.updated", {"section": key, "title": REPORT_KEYS[key], "content": result[key]})
        return result


def _demo_snapshot(
    symbol: str,
    asset_type: str,
    analysis_date: str | None = None,
) -> dict[str, Any] | None:
    if asset_type != "fund":
        return None
    prices = [
        {"date": "2026-01-02", "adjusted_close": 580.0, "benchmark": 580.0},
        {"date": "2026-02-02", "adjusted_close": 592.0, "benchmark": 589.0},
        {"date": "2026-03-02", "adjusted_close": 574.0, "benchmark": 570.0},
        {"date": "2026-04-01", "adjusted_close": 606.0, "benchmark": 600.0},
        {"date": "2026-05-01", "adjusted_close": 620.0, "benchmark": 611.0},
        {"date": "2026-06-01", "adjusted_close": 634.0, "benchmark": 624.0},
        {
            "date": analysis_date or "2026-07-21",
            "adjusted_close": 642.0,
            "benchmark": 630.0,
        },
    ]
    holdings = [] if symbol == "EMPTY" else [
        {"symbol": "NVDA", "name": "NVIDIA", "weight": 0.078},
        {"symbol": "MSFT", "name": "Microsoft", "weight": 0.069},
        {"symbol": "AAPL", "name": "Apple", "weight": 0.061},
        {"symbol": "AMZN", "name": "Amazon", "weight": 0.039},
    ]
    warnings = ["Profile and holdings are latest available metadata, not historical point-in-time data."]
    if not holdings:
        warnings.append("Top holdings are unavailable for this fund.")
    return {
        "instrument": {"canonical_symbol": symbol, "name": "SPDR S&P 500 ETF Trust", "fund_type": "etf", "exchange": "PCX", "currency": "USD"},
        "profile": {"category": "Large Blend", "total_assets": 650000000000, "expense_ratio": 0.000945, "yield_value": 0.012, "nav": 641.82, "market_price": 642.0},
        "metrics": [
            {"name": "total_return", "window": "1m", "value": 0.018, "unit": "percent"},
            {"name": "total_return", "window": "1y", "value": 0.107, "unit": "percent"},
            {"name": "annualized_volatility", "value": 0.142, "unit": "percent"},
            {"name": "maximum_drawdown", "value": -0.061, "unit": "percent"},
            {"name": "tracking_error", "value": 0.008, "unit": "percent"},
        ],
        "price_series": prices,
        "top_holdings": holdings,
        "sectors": {"Technology": 0.32, "Financial Services": 0.14, "Healthcare": 0.11, "Consumer Cyclical": 0.10},
        "warnings": warnings,
        "source": "demo-yfinance",
    }
