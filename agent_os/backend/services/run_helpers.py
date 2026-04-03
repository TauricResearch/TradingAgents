"""Run-level helpers shared across the LangGraphEngine.

Contains error classification (policy / rate-limit), LLM fallback
configuration, analysis status inspection, and price fetching.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_os.backend.store import runs as live_runs

logger = logging.getLogger("agent_os.engine")


# ---------------------------------------------------------------------------
# LLM policy / 404 error helpers
# ---------------------------------------------------------------------------


def is_policy_error(exc: Exception) -> bool:
    """Return True if *exc* is a provider 404 / guardrail / policy error."""
    if getattr(exc, "status_code", None) == 404:
        return True
    cause = getattr(exc, "__cause__", None)
    if getattr(cause, "status_code", None) == 404:
        return True
    msg = str(exc).lower()
    return "404" in msg and ("policy" in msg or "guardrail" in msg or "openrouter" in msg)


def is_rate_limit_error(exc: Exception) -> bool:
    """Return True if *exc* looks like a temporary upstream/provider rate limit."""
    if getattr(exc, "status_code", None) == 429:
        return True
    cause = getattr(exc, "__cause__", None)
    if getattr(cause, "status_code", None) == 429:
        return True
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "temporarily rate-limited upstream",
            "retry shortly",
            "rate limited upstream",
            "rate-limited upstream",
            "rate limit",
            "429",
        )
    )


def is_fallback_eligible_error(exc: Exception) -> bool:
    """Return True if *exc* should trigger per-tier fallback LLM substitution."""
    return is_policy_error(exc) or is_rate_limit_error(exc)


def build_fallback_config(config: dict) -> dict | None:
    """Return config with per-tier fallback models substituted, or None if none set."""
    tiers = ("quick_think", "mid_think", "deep_think")
    replacements: dict = {}
    for tier in tiers:
        fb_llm = config.get(f"{tier}_fallback_llm")
        fb_prov = config.get(f"{tier}_fallback_llm_provider")
        if fb_llm:
            replacements[f"{tier}_llm"] = fb_llm
        if fb_prov:
            replacements[f"{tier}_llm_provider"] = fb_prov
    if not replacements:
        return None
    return {**config, **replacements}


def fallback_model_summary(current_config: dict, fallback_config: dict) -> str:
    return ", ".join(
        f"{tier}={fallback_config.get(f'{tier}_llm', 'same')}"
        for tier in ("quick_think", "mid_think", "deep_think")
        if fallback_config.get(f"{tier}_llm") != current_config.get(f"{tier}_llm")
    )


# ---------------------------------------------------------------------------
# Analysis status helpers
# ---------------------------------------------------------------------------


def analysis_status(analysis: Any) -> str:
    """Return the normalized analysis status for a saved ticker artifact."""
    if not isinstance(analysis, dict):
        return "missing"
    status = str(analysis.get("analysis_status") or "").strip().lower()
    has_final_decision = bool(str(analysis.get("final_trade_decision") or "").strip())
    if status == "aborted":
        return status
    if has_final_decision:
        return "completed"
    if status:
        return status
    return "incomplete"


def analysis_is_terminal(analysis: Any) -> bool:
    return analysis_status(analysis) in {"completed", "aborted"}


def analysis_has_deep_dive(analysis: Any) -> bool:
    """Return True when a ticker analysis contains a completed deep-dive output."""
    if not isinstance(analysis, dict):
        return False
    status = str(analysis.get("analysis_status") or "").strip().lower()
    if status == "aborted":
        return False
    if status == "completed":
        return True
    return bool(str(analysis.get("final_trade_decision") or "").strip())


def normalize_analysis_status(analysis: dict[str, Any]) -> str:
    """Persist a terminal status whenever a final trade decision is present."""
    status = str(analysis.get("analysis_status") or "").strip().lower()
    if status == "aborted":
        return status
    if str(analysis.get("final_trade_decision") or "").strip():
        return "completed"
    if status:
        return status
    return "incomplete"


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------


def run_should_stop(run_id: str) -> bool:
    """Return True when a graceful stop has been requested for the root run."""
    return bool((live_runs.get(run_id) or {}).get("stop_requested"))


# ---------------------------------------------------------------------------
# Price fetching
# ---------------------------------------------------------------------------


def fetch_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch the latest closing price for each ticker via yfinance.

    Returns a dict of {ticker: price}.  Tickers that fail are silently skipped.
    """
    if not tickers:
        return {}
    try:
        import math

        import yfinance as yf

        data = yf.download(tickers, period="2d", auto_adjust=True, progress=False, threads=True)
        if data.empty:
            return {}
        close = data["Close"] if "Close" in data.columns else data
        last_row = close.iloc[-1]
        return {
            t: float(last_row[t])
            for t in tickers
            if t in last_row.index and not math.isnan(last_row[t])
        }
    except Exception as exc:
        logger.warning("fetch_prices failed: %s", exc)
        return {}


def tickers_from_decision(decision: dict) -> list[str]:
    """Extract all ticker symbols referenced in a PM decision dict."""
    tickers = set()
    for key in ("sells", "buys", "holds"):
        for item in decision.get(key) or []:
            if isinstance(item, dict):
                t = item.get("ticker") or item.get("symbol")
            else:
                t = str(item)
            if t:
                tickers.add(t.upper())
    return list(tickers)
