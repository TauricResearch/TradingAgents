"""Run-level helpers shared across the LangGraphEngine.

Contains error classification (policy / rate-limit), LLM fallback
configuration, analysis status inspection, and price fetching.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_os.backend.store import runs as live_runs

logger = logging.getLogger("agent_os.engine")

_LLM_TIERS = ("quick_think", "mid_think", "deep_think")

# Keep backend defaults aligned with client/provider adapters.
_PROVIDER_DEFAULT_BACKEND_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "xai": "https://api.x.ai/v1",
    "ollama": "http://localhost:11434",
    "anthropic": "https://api.anthropic.com",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai/",
}


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


def infer_fallback_tier(config: dict[str, Any], exc: Exception) -> str | None:
    """Infer which LLM tier failed based on model-id hints in the exception text.

    Returns:
        The matched tier name when exactly one tier model is found in the error,
        otherwise None.
    """
    msg = str(exc).lower()
    matched_tiers: list[str] = []
    for tier in _LLM_TIERS:
        model = str(config.get(f"{tier}_llm") or "").strip().lower()
        if model and model in msg:
            matched_tiers.append(tier)
    if len(matched_tiers) == 1:
        return matched_tiers[0]
    return None


def build_fallback_config(config: dict[str, Any], tier: str | None = None) -> dict | None:
    """Return config with fallback substitution.

    Args:
        config: Current runtime config.
        tier: Target tier to substitute. When provided, only that tier is
              replaced (e.g. "mid_think"). When None or unrecognised, all
              configured tier fallbacks are applied as a safe default.
    """
    tiers = (tier,) if tier in _LLM_TIERS else _LLM_TIERS

    replacements: dict = {}
    for tier in tiers:
        fb_llm = config.get(f"{tier}_fallback_llm")
        fb_prov = config.get(f"{tier}_fallback_llm_provider")
        if fb_llm:
            replacements[f"{tier}_llm"] = fb_llm
        if fb_prov:
            provider = str(fb_prov).strip().lower()
            replacements[f"{tier}_llm_provider"] = provider
            fallback_backend_url = _PROVIDER_DEFAULT_BACKEND_URLS.get(provider)
            if fallback_backend_url:
                replacements[f"{tier}_backend_url"] = fallback_backend_url
    if not replacements:
        return None
    return {**config, **replacements}


def fallback_model_summary(current_config: dict, fallback_config: dict) -> str:
    return ", ".join(
        f"{tier}={fallback_config.get(f'{tier}_llm', 'same')}"
        for tier in _LLM_TIERS
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
    # Check the structured decision payload as an alternative signal — the PM
    # node populates this even when final_trade_decision text is empty (e.g.
    # when the LLM returned empty content and a fallback was applied).
    structured = analysis.get("final_trade_decision_structured") or {}
    if isinstance(structured, dict) and structured.get("status") == "completed":
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
