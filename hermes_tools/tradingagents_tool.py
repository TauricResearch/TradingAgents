"""Hermes tool: tradingagents_analyze

Wraps TradingAgentsGraph.propagate() as a Hermes-callable tool.

LLM provider and model are read from env vars at call time so the tool
stays LLM-agnostic — Hermes configures the backend; this module never
hardcodes a provider.

Env vars consumed:
    HERMES_LLM_PROVIDER     LLM provider key (default: "openai")
    HERMES_LLM_MODEL        Model name for deep/quick thinking (default: "gpt-4o")
    HERMES_LLM_BACKEND_URL  Optional custom base URL for the provider
    TRADINGAGENTS_*         Standard TradingAgents env-var overrides (passed
                            through; default_config.py applies them automatically)
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_date(date_str: str) -> str:
    """Return a YYYY-MM-DD string; 'latest' resolves to today."""
    if date_str.lower() == "latest":
        return date.today().isoformat()
    # Validate format to surface bad input early.
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        raise ValueError(f"date must be YYYY-MM-DD or 'latest', got: {date_str!r}")
    return date_str


def _build_config() -> dict[str, Any]:
    """Build TradingAgentsGraph config from env vars.

    Imports DEFAULT_CONFIG (which already applies TRADINGAGENTS_* overrides)
    and then layers on the HERMES_LLM_* env vars so the Hermes operator's
    runtime LLM choice takes precedence.
    """
    from tradingagents.default_config import DEFAULT_CONFIG

    cfg = dict(DEFAULT_CONFIG)  # shallow copy — safe for string/scalar values

    provider = os.environ.get("HERMES_LLM_PROVIDER", "").strip()
    model = os.environ.get("HERMES_LLM_MODEL", "").strip()
    backend_url = os.environ.get("HERMES_LLM_BACKEND_URL", "").strip() or None

    if provider:
        cfg["llm_provider"] = provider
    if model:
        cfg["deep_think_llm"] = model
        cfg["quick_think_llm"] = model
    if backend_url:
        cfg["backend_url"] = backend_url

    return cfg


def _extract_trader_fields(trader_plan: str) -> dict[str, Any]:
    """Pull entry_price, stop_loss, position_sizing from rendered TraderProposal markdown.

    The renderer in schemas.py produces lines like:
        **Entry Price**: 185.0
        **Stop Loss**: 178.5
        **Position Sizing**: 5% of portfolio
    Values are optional in the schema so we return None when absent.
    """
    fields: dict[str, Any] = {
        "entry_price": None,
        "stop_loss": None,
        "position_sizing": None,
    }
    patterns = {
        "entry_price":    r"\*\*Entry Price\*\*:\s*([\d.]+)",
        "stop_loss":      r"\*\*Stop Loss\*\*:\s*([\d.]+)",
        "position_sizing": r"\*\*Position Sizing\*\*:\s*(.+)",
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, trader_plan)
        if m:
            raw = m.group(1).strip()
            if key in ("entry_price", "stop_loss"):
                try:
                    fields[key] = float(raw)
                except ValueError:
                    pass
            else:
                fields[key] = raw
    return fields


def _determine_analysts_fired(final_state: dict[str, Any]) -> list[str]:
    """Return names of analysts whose reports are non-empty in this run."""
    mapping = {
        "market":       "market_report",
        "social":       "sentiment_report",
        "news":         "news_report",
        "fundamentals": "fundamentals_report",
    }
    return [name for name, key in mapping.items() if final_state.get(key, "").strip()]


# ---------------------------------------------------------------------------
# Public tool function
# ---------------------------------------------------------------------------

def tradingagents_analyze(ticker: str, date: str = "latest") -> dict:
    """Run full TradingAgents multi-agent analysis on a ticker.

    Args:
        ticker: Stock ticker symbol, e.g. "AAPL".
        date:   Trade date as YYYY-MM-DD, or "latest" for today.

    Returns:
        A dict with keys:
            ticker, date, signal, entry_price, stop_loss, position_sizing,
            scenario, analysts_fired, confidence, error (on failure only).
        signal is one of: Buy / Overweight / Hold / Underweight / Sell.
    """
    if not ticker or not ticker.strip():
        return {"error": "ticker must be a non-empty string"}

    ticker = ticker.strip().upper()

    try:
        trade_date = _resolve_date(date)
    except ValueError as exc:
        return {"error": str(exc)}

    logger.info("tradingagents_analyze: starting analysis for %s on %s", ticker, trade_date)
    t0 = time.monotonic()

    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        cfg = _build_config()
        graph = TradingAgentsGraph(
            selected_analysts=["market", "social", "news", "fundamentals"],
            debug=False,
            config=cfg,
        )

        final_state, signal = graph.propagate(ticker, trade_date)

    except Exception as exc:
        logger.exception("tradingagents_analyze: analysis failed for %s", ticker)
        return {"error": str(exc)}

    elapsed = time.monotonic() - t0
    logger.info(
        "tradingagents_analyze: finished %s in %.1fs — signal=%s",
        ticker, elapsed, signal,
    )

    trader_plan: str = final_state.get("trader_investment_plan", "")
    trader_fields = _extract_trader_fields(trader_plan)
    analysts_fired = _determine_analysts_fired(final_state)

    # Scenario: first non-empty analyst report excerpt (truncated) so
    # the approval card has a human-readable context line.
    scenario = ""
    for key in ("market_report", "news_report", "sentiment_report", "fundamentals_report"):
        text = final_state.get(key, "").strip()
        if text:
            # Grab the first sentence or up to 200 chars.
            end = text.find(". ")
            scenario = text[: end + 1] if end != -1 else text[:200]
            break

    # Confidence: heuristic — number of analysts that fired / total possible.
    confidence = round(len(analysts_fired) / 4.0, 2)

    return {
        "ticker": ticker,
        "date": trade_date,
        "signal": signal,
        "entry_price": trader_fields["entry_price"],
        "stop_loss": trader_fields["stop_loss"],
        "position_sizing": trader_fields["position_sizing"],
        "scenario": scenario,
        "analysts_fired": analysts_fired,
        "confidence": confidence,
    }
