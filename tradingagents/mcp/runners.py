"""Input validation and the work run by MCP background jobs.

Kept separate from the MCP tool layer so the analysis pipeline can be tested
without a running server, and so the server module only deals with protocol
concerns.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from tradingagents.agents.rating import is_review, run_rating
from tradingagents.backtest import iter_grid, run_backtest, summarize
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.symbols import crypto_base, normalize_symbol
from tradingagents.default_config import build_default_config
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.portfolio import PortfolioContext

from .jobs import Job, JobCancelled

logger = logging.getLogger(__name__)

ANALYSTS = ("market", "social", "news", "fundamentals")
ANALYST_ALIASES = {"sentiment": "social"}
ASSET_TYPES = ("stock", "crypto")

ALLOWED_CONFIG_OVERRIDES = frozenset(
    {
        "llm_provider",
        "deep_think_llm",
        "quick_think_llm",
        "deep_think_provider",
        "quick_think_provider",
        "backend_url",
        "deep_think_backend_url",
        "quick_think_backend_url",
        "google_thinking_level",
        "openai_reasoning_effort",
        "anthropic_effort",
        "temperature",
        "max_tokens",
        "output_language",
        "max_debate_rounds",
        "max_risk_discuss_rounds",
        "max_tool_rounds",
        "max_recur_limit",
        "checkpoint_enabled",
        "benchmark_ticker",
        "holding_period_days",
        "news_article_limit",
        "global_news_article_limit",
        "global_news_lookback_days",
        "data_vendors",
        "tool_vendors",
    }
)

_TICKER_CHARS = frozenset("._-^=")

_STAGE_FIELDS = (
    ("market_report", "market analyst report ready"),
    ("sentiment_report", "sentiment analyst report ready"),
    ("news_report", "news analyst report ready"),
    ("fundamentals_report", "fundamentals analyst report ready"),
    ("investment_plan", "research manager plan ready"),
    ("trader_investment_plan", "trader plan ready"),
    ("final_trade_decision", "portfolio manager decision ready"),
)


def normalize_ticker(raw: str) -> str:
    """A canonical Yahoo symbol, or a ValueError naming what is wrong."""
    value = str(raw).strip()
    if (
        not value
        or len(value) > 32
        or not all(character.isalnum() or character in _TICKER_CHARS for character in value)
    ):
        raise ValueError(f"not a ticker symbol: {raw!r} (examples: AAPL, 0700.HK, BTC-USD, GC=F)")
    return normalize_symbol(value)


def resolve_tickers(raw: list[str] | str) -> list[str]:
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    if not raw:
        raise ValueError("name at least one ticker")
    tickers = [normalize_ticker(ticker) for ticker in raw]
    return list(dict.fromkeys(tickers))


def validate_date(raw: str, field_name: str = "date") -> str:
    """A canonical YYYY-MM-DD date no later than today."""
    value = str(raw).strip()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"{field_name} must be YYYY-MM-DD, got {raw!r}") from None
    if parsed.strftime("%Y-%m-%d") != value:
        raise ValueError(f"{field_name} must be YYYY-MM-DD, got {raw!r}")
    if value > get_current_date():
        raise ValueError(f"{field_name} cannot be in the future: {value}")
    return value


def detect_asset_type(ticker: str) -> str:
    return "crypto" if crypto_base(ticker) else "stock"


def resolve_asset_type(ticker: str, raw: str | None) -> str:
    if raw is None:
        return detect_asset_type(ticker)
    value = str(raw).strip().lower()
    if value not in ASSET_TYPES:
        raise ValueError(f"asset_type must be one of {', '.join(ASSET_TYPES)}, got {raw!r}")
    return value


def resolve_analysts(raw: list[str] | str | None, asset_type: str) -> list[str]:
    """Canonical analyst keys, in the framework's order, valid for the asset type."""
    if raw is None:
        names: list[str] = []
    elif isinstance(raw, str):
        names = [part.strip() for part in raw.split(",") if part.strip()]
    else:
        names = [str(part).strip() for part in raw if str(part).strip()]

    if not names:
        selected = list(ANALYSTS)
    else:
        selected = []
        for name in names:
            key = ANALYST_ALIASES.get(name.lower(), name.lower())
            if key not in ANALYSTS:
                choices = ", ".join("sentiment" if a == "social" else a for a in ANALYSTS)
                raise ValueError(f"unknown analyst {name!r}; choose from {choices}")
            if key not in selected:
                selected.append(key)
        selected = [analyst for analyst in ANALYSTS if analyst in selected]

    if asset_type == "crypto" and "fundamentals" in selected:
        raise ValueError("the fundamentals analyst is not available for crypto")
    return selected


def resolve_portfolio(raw: dict[str, Any] | None) -> PortfolioContext | None:
    if raw is None:
        return None
    try:
        return PortfolioContext.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"portfolio is not usable: {exc}") from None


def build_run_config(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """The built-in defaults plus per-run overrides, validated against an allowlist."""
    config = build_default_config()
    if not overrides:
        return config
    if not isinstance(overrides, dict):
        raise ValueError("config must be an object of TradingAgents settings")
    unknown = sorted(set(overrides) - ALLOWED_CONFIG_OVERRIDES)
    if unknown:
        raise ValueError(
            f"config key(s) not allowed from MCP: {', '.join(unknown)}; "
            f"allowed: {', '.join(sorted(ALLOWED_CONFIG_OVERRIDES))}"
        )
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key].update(value)
        else:
            config[key] = value
    return config


def stage_from_state(state: dict[str, Any]) -> str:
    stage = "analysts working"
    for key, label in _STAGE_FIELDS:
        if state.get(key):
            stage = label
    return stage


def _progress_from_state(state: dict[str, Any]) -> float:
    present = sum(1 for key, _label in _STAGE_FIELDS if state.get(key))
    return 100.0 * present / len(_STAGE_FIELDS)


def reports_from_state(state: dict[str, Any]) -> dict[str, str]:
    """The report sections an external client can ask for by name."""
    research_parts = []
    if state.get("investment_debate_state"):
        debate = state["investment_debate_state"]
        if debate.get("bull_history"):
            research_parts.append(f"### Bull Researcher\n{debate['bull_history']}")
        if debate.get("bear_history"):
            research_parts.append(f"### Bear Researcher\n{debate['bear_history']}")
    if state.get("investment_plan"):
        research_parts.append(f"### Research Manager\n{state['investment_plan']}")

    risk_parts = []
    if state.get("risk_debate_state"):
        risk = state["risk_debate_state"]
        for label, key in (
            ("Aggressive Analyst", "aggressive_history"),
            ("Conservative Analyst", "conservative_history"),
            ("Neutral Analyst", "neutral_history"),
        ):
            if risk.get(key):
                risk_parts.append(f"### {label}\n{risk[key]}")

    return {
        "market": state.get("market_report") or "",
        "sentiment": state.get("sentiment_report") or "",
        "news": state.get("news_report") or "",
        "fundamentals": state.get("fundamentals_report") or "",
        "research": "\n\n".join(research_parts),
        "trader": state.get("trader_investment_plan") or "",
        "risk": "\n\n".join(risk_parts),
        "decision": state.get("final_trade_decision") or "",
    }


def run_analysis_job(job: Job) -> dict[str, Any]:
    """Run one full graph, streaming so the job's stage tracks the analysts."""
    params = job.params
    ticker = params["ticker"]
    trade_date = params["trade_date"]
    asset_type = params["asset_type"]
    analysts = params["analysts"]
    portfolio = params.get("portfolio")
    config = build_run_config(params.get("config"))

    graph = TradingAgentsGraph(analysts, config=config, debug=False)
    init_state = graph.create_run_state(ticker, trade_date, asset_type, portfolio)
    args = graph.propagator.get_graph_args()

    thread_id = graph.begin_checkpoint(ticker, trade_date, asset_type, portfolio)
    if thread_id is not None:
        args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = thread_id

    final_state: dict[str, Any] = {}
    notes: list[str] = []
    try:
        for _messages, chunk in graph.stream_run(graph.checkpoint_input(init_state), **args):
            if job.cancel_requested:
                raise JobCancelled()
            if chunk is not None:
                final_state.update(chunk)
                job.update(
                    stage=stage_from_state(final_state),
                    progress=_progress_from_state(final_state),
                )

        final_state.pop("messages", None)

        try:
            graph.record_decision(ticker, trade_date, final_state)
        except Exception as exc:
            logger.warning("Could not record %s %s in the memory log: %s", ticker, trade_date, exc)
            notes.append(
                f"the decision was not added to the memory log ({type(exc).__name__}: {exc})"
            )
        try:
            graph.clear_checkpoint_on_success(ticker, trade_date, asset_type, portfolio)
        except Exception as exc:
            logger.warning("Could not clear the checkpoint for %s %s: %s", ticker, trade_date, exc)
            notes.append(f"the checkpoint was not cleared ({type(exc).__name__}: {exc})")
    finally:
        graph.end_checkpoint()

    rating = run_rating(final_state)
    report_path = None
    html_path = None
    if params.get("save_reports", True):
        try:
            path = graph.save_reports(final_state, ticker, html=params.get("html", True))
            report_path = str(path)
            if params.get("html", True):
                html_path = str(Path(path).parent / "complete_report.html")
        except Exception as exc:
            logger.warning("Could not save the report for %s %s: %s", ticker, trade_date, exc)
            notes.append(f"the report could not be saved ({type(exc).__name__}: {exc})")

    return {
        "kind": "analysis",
        "ticker": ticker,
        "trade_date": trade_date,
        "asset_type": asset_type,
        "analysts": analysts,
        "rating": rating,
        "needs_review": is_review(rating),
        "decision": final_state.get("final_trade_decision") or "",
        "reports": reports_from_state(final_state),
        "report_path": report_path,
        "html_path": html_path,
        "report_dir": str(Path(report_path).parent) if report_path else None,
        "run_settings": graph.run_settings(),
        "notes": notes,
    }


def run_backtest_job(job: Job) -> dict[str, Any]:
    """Run a ticker/date grid and score the settled decisions."""
    params = job.params
    config = build_run_config(params.get("config"))
    dates = iter_grid(params["start_date"], params["end_date"], params["every_n_days"])

    def progress(done: int, total: int, ticker: str, date: str) -> None:
        if job.cancel_requested:
            raise JobCancelled()
        job.update(
            stage=f"{ticker} on {date}",
            detail=f"cell {done}/{total}",
            progress=100.0 * done / max(total, 1),
        )

    result = run_backtest(
        params["tickers"],
        dates,
        config,
        asset_type=params["asset_type"],
        portfolio=params.get("portfolio"),
        selected_analysts=params["analysts"],
        run_id=params.get("run_id"),
        progress=progress,
    )

    summary = None
    notes: list[str] = []
    try:
        summary = summarize(result).render()
    except Exception as exc:
        logger.warning("Could not summarize backtest %s: %s", result.run_id, exc)
        notes.append(f"the summary could not be built ({type(exc).__name__}: {exc})")

    return {
        "kind": "backtest",
        "run_id": result.run_id,
        "tickers": params["tickers"],
        "start_date": params["start_date"],
        "end_date": params["end_date"],
        "every_n_days": params["every_n_days"],
        "asset_type": params["asset_type"],
        "analysts": params["analysts"],
        "cells_run": result.cells_run,
        "skipped": result.skipped,
        "failures": [list(failure) for failure in result.failures],
        "settlement_failures": [list(failure) for failure in result.settlement_failures],
        "log_path": str(result.log_path),
        "summary": summary,
        "notes": notes,
    }
