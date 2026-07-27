"""Deterministic metadata for comparing and auditing TradingAgents runs."""

from __future__ import annotations

import hashlib
import json
from importlib import metadata
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from tradingagents.agents.utils.rating import parse_rating

_CONFIG_KEYS = (
    "llm_provider",
    "deep_think_llm",
    "quick_think_llm",
    "backend_url",
    "google_thinking_level",
    "openai_reasoning_effort",
    "anthropic_effort",
    "temperature",
    "llm_max_retries",
    "output_language",
    "max_debate_rounds",
    "max_risk_discuss_rounds",
    "max_recur_limit",
    "checkpoint_enabled",
    "news_article_limit",
    "global_news_article_limit",
    "global_news_lookback_days",
    "global_news_queries",
    "data_vendors",
    "tool_vendors",
    "benchmark_ticker",
    "benchmark_map",
)


def _json_value(value: Any) -> Any:
    """Convert common config values to stable, JSON-serializable values."""
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_backend_url(value: Any) -> str | None:
    """Keep endpoint identity while dropping credentials, query strings, and fragments."""
    if value is None or value == "":
        return None

    parsed = urlsplit(str(value))
    if not parsed.scheme or not parsed.hostname:
        # Do not risk copying credentials from an unusual, non-URL endpoint
        # string into a report intended for sharing.
        return "<custom>"

    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def _package_version() -> str | None:
    try:
        return metadata.version("tradingagents")
    except metadata.PackageNotFoundError:
        return None


def build_run_manifest(
    config: dict[str, Any],
    final_state: dict[str, Any],
    ticker: str,
    selected_analysts: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    """Build a shareable manifest for a completed run.

    The manifest records requested inputs and configured vendor identifiers. It
    deliberately does not claim that a configured fallback vendor served any
    particular tool call; live-source capture/replay is a separate concern.
    """
    effective_config = {
        key: _json_value(config[key])
        for key in _CONFIG_KEYS
        if key in config
    }
    if "backend_url" in effective_config:
        effective_config["backend_url"] = _safe_backend_url(config.get("backend_url"))

    canonical_config = json.dumps(
        effective_config,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    decision = str(final_state.get("final_trade_decision") or "")
    past_context = str(final_state.get("past_context") or "")
    instrument_context = str(final_state.get("instrument_context") or "")

    return {
        "schema_version": "1",
        "software": {
            "package": "tradingagents",
            "version": _package_version(),
        },
        "run": {
            "ticker": ticker,
            "requested_as_of": (
                str(final_state["trade_date"])
                if final_state.get("trade_date") is not None
                else None
            ),
            "asset_type": final_state.get("asset_type"),
            "selected_analysts": list(selected_analysts),
        },
        "models": {
            "provider": config.get("llm_provider"),
            "deep": config.get("deep_think_llm"),
            "quick": config.get("quick_think_llm"),
        },
        "configured_data_sources": {
            "category_vendor_ids": _json_value(config.get("data_vendors", {})),
            "tool_vendor_ids": _json_value(config.get("tool_vendors", {})),
        },
        "configuration": effective_config,
        "configuration_sha256": _sha256_text(canonical_config),
        "context": {
            "instrument_context_sha256": (
                _sha256_text(instrument_context) if instrument_context else None
            ),
            "memory_context_sha256": (
                _sha256_text(past_context) if past_context else None
            ),
        },
        "output": {
            "final_rating": parse_rating(decision) if decision else None,
            "final_trade_decision_sha256": (
                _sha256_text(decision) if decision else None
            ),
        },
    }
