"""Run manifest.

A small, auditable record written alongside each run's results: what model and
provider produced it, which API keys were present (booleans only — never the
values), which data sources were configured/usable, the analysts involved, and
the usage tally. Makes runs comparable and reproducible-in-intent even though
LLM output is not bit-identical.
"""

from __future__ import annotations

import datetime
import os
from typing import Any

from tradingagents.config_validation import VENDOR_API_KEY_ENV
from tradingagents.llm_clients.api_key_env import get_api_key_env


def _relevant_key_envs(config: dict) -> list[str]:
    """Env-var names worth recording presence for: the LLM provider's key plus
    every data-vendor key. De-duplicated, stable order."""
    names: list[str] = []
    provider = str(config.get("llm_provider", "")).lower()
    llm_key = get_api_key_env(provider)
    if llm_key:
        names.append(llm_key)
    for key in VENDOR_API_KEY_ENV.values():
        if key and key not in names:
            names.append(key)
    return names


def build_manifest(
    config: dict,
    ticker: str,
    trade_date,
    selected_analysts,
    preflight: Any | None = None,
    usage: Any | None = None,
    env: dict | None = None,
) -> dict:
    """Assemble the manifest dict (the graph serializes it to manifest.json)."""
    env = os.environ if env is None else env

    manifest: dict[str, Any] = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "ticker": ticker,
        "trade_date": str(trade_date),
        "selected_analysts": list(selected_analysts),
        "llm": {
            "provider": config.get("llm_provider"),
            "deep_think_llm": config.get("deep_think_llm"),
            "quick_think_llm": config.get("quick_think_llm"),
            "backend_url": config.get("backend_url"),
            "temperature": config.get("temperature"),
        },
        "data_vendors": dict(config.get("data_vendors", {})),
        # Presence only — never the secret values.
        "api_keys_present": {name: bool(env.get(name)) for name in _relevant_key_envs(config)},
    }

    if preflight is not None:
        manifest["preflight"] = {
            "ok": getattr(preflight, "ok", None),
            "missing_required": list(getattr(preflight, "missing_required", []) or []),
            "missing_optional": list(getattr(preflight, "missing_optional", []) or []),
        }

    if usage is not None:
        manifest["usage"] = usage.summary() if hasattr(usage, "summary") else dict(usage)

    return manifest
