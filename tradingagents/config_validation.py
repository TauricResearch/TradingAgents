"""Preflight configuration validation.

Catch missing data-source API keys at startup (second 0) rather than deep
inside an analyst node after minutes of paid LLM calls. Maps the selected
analysts to the data categories they can call, resolves each category's
configured vendor chain, and checks whether at least one vendor in that chain
is usable (keyless, or its API key is present in the environment).

Missing *optional* (enrichment) sources only warn — the router degrades them
gracefully at runtime (see ``dataflows.interface.OPTIONAL_CATEGORIES``). Missing
*required* (core) sources are reported as errors and, when ``strict`` is set,
raise before the run starts.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Data vendor -> environment variable holding its API key (None = keyless).
VENDOR_API_KEY_ENV: dict[str, str | None] = {
    "yfinance": None,
    "polymarket": None,
    "fred": "FRED_API_KEY",
    "alpha_vantage": "ALPHA_VANTAGE_API_KEY",
}

# Which data categories each analyst type can pull from (mirrors the ToolNode
# wiring in TradingAgentsGraph._create_tool_nodes).
ANALYST_CATEGORIES: dict[str, list[str]] = {
    "market": ["core_stock_apis", "technical_indicators"],
    "social": ["news_data"],
    "news": ["news_data", "macro_data", "prediction_markets"],
    "fundamentals": ["fundamental_data"],
}

# Enrichment categories — missing keys here are non-fatal (kept in sync with
# dataflows.interface.OPTIONAL_CATEGORIES).
OPTIONAL_CATEGORIES = {"macro_data", "prediction_markets"}

# Values that mean "this category is turned off" (kept in sync with
# dataflows.interface.DISABLED_VENDOR_SENTINELS). A disabled category is skipped,
# not reported as a missing source.
DISABLED_VENDOR_SENTINELS = {"", "none", "off", "disabled"}


@dataclass
class PreflightResult:
    """Outcome of validate_config."""

    ok: bool = True  # False when a required (core) category is unsatisfiable
    warnings: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)


def _category_vendors(category: str) -> list[str]:
    """All vendors that can serve any tool in ``category`` (lazy import to keep
    this module cheap to import)."""
    from tradingagents.dataflows.interface import TOOLS_CATEGORIES, VENDOR_METHODS

    vendors: list[str] = []
    for tool in TOOLS_CATEGORIES.get(category, {}).get("tools", []):
        for vendor in VENDOR_METHODS.get(tool, {}):
            if vendor not in vendors:
                vendors.append(vendor)
    return vendors


def _configured_chain(config: dict, category: str) -> list[str]:
    """The vendor chain for ``category``: the explicit config, or — for the
    "default" sentinel / unset — all vendors that can serve the category."""
    raw = config.get("data_vendors", {}).get(category, "default")
    if raw is None or str(raw).strip().lower() in DISABLED_VENDOR_SENTINELS:
        return []  # disabled -> skipped, not a missing source
    explicit = [v.strip() for v in str(raw).split(",") if v.strip() and v.strip() != "default"]
    return explicit if explicit else _category_vendors(category)


def _vendor_usable(vendor: str, env: dict) -> bool:
    """A vendor is usable if it's keyless or its API-key env var is set."""
    key_env = VENDOR_API_KEY_ENV.get(vendor)
    if key_env is None:  # keyless (or unknown vendor — don't block on it)
        return vendor in VENDOR_API_KEY_ENV  # known keyless -> usable
    return bool(env.get(key_env))


def validate_config(
    selected_analysts, config: dict, env: dict | None = None
) -> PreflightResult:
    """Check that the data sources the selected analysts need are usable.

    Args:
        selected_analysts: iterable of analyst names ("market", "news", ...).
        config: the resolved run config (uses ``config["data_vendors"]``).
        env: environment mapping to check keys against (defaults to os.environ).

    Returns:
        PreflightResult with human-readable warnings and the missing categories.
    """
    env = os.environ if env is None else env
    result = PreflightResult()

    # Unique categories across the selected analysts, in a stable order.
    categories: list[str] = []
    for analyst in selected_analysts:
        for cat in ANALYST_CATEGORIES.get(analyst, []):
            if cat not in categories:
                categories.append(cat)

    for category in categories:
        chain = _configured_chain(config, category)
        if not chain:
            # Category explicitly disabled ("off"/"none"); handled at runtime.
            continue
        if any(_vendor_usable(v, env) for v in chain):
            continue

        # No vendor in the chain is usable — collect the keys that would fix it.
        needed = sorted(
            {VENDOR_API_KEY_ENV[v] for v in chain if VENDOR_API_KEY_ENV.get(v)}
        )
        keys_hint = " or ".join(needed) if needed else "(no API key configured)"
        if category in OPTIONAL_CATEGORIES:
            result.missing_optional.append(category)
            result.warnings.append(
                f"Optional data source '{category}' has no usable vendor "
                f"(set {keys_hint}); it will be skipped at runtime."
            )
        else:
            result.ok = False
            result.missing_required.append(category)
            result.warnings.append(
                f"Required data source '{category}' has no usable vendor "
                f"(set {keys_hint}); analysts depending on it may fail."
            )

    return result


def enforce_preflight(selected_analysts, config: dict, strict: bool = False) -> PreflightResult:
    """Run validate_config, log every warning loudly, and (if strict) raise on a
    missing *required* source. Returns the result for callers/tests."""
    result = validate_config(selected_analysts, config)
    for warning in result.warnings:
        logger.warning("preflight: %s", warning)
    if not result.ok and strict:
        raise ValueError(
            "Preflight check failed — missing required data sources: "
            f"{', '.join(result.missing_required)}. "
            "Set the indicated API keys, disable those categories in "
            "config['data_vendors'], or drop the analysts that need them."
        )
    return result
