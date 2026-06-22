"""Read-only ``capabilities`` subcommand.

Dumps the provider / model / capability / vendor / language surface as one JSON
object so the native Settings UI sources its lists from the engine and never
drifts from it. Runs in the same bundled interpreter as runs do.

Imports ``tradingagents`` (Python >=3.10).
"""

from __future__ import annotations

import dataclasses
from typing import Any

from desk_adapter.protocol import Emitter

# Native (non OpenAI-compatible) providers route through dedicated clients in
# tradingagents/llm_clients/factory.py.
_NATIVE = {"anthropic", "google", "azure", "bedrock"}

# Static UI value lists (the engine consumes these but exposes no enum to read).
_REASONING_KNOBS = {
    "openai_reasoning_effort": ["low", "medium", "high"],
    "anthropic_effort": ["low", "medium", "high"],
    "google_thinking_level": ["minimal", "high"],
}
_OUTPUT_LANGUAGES = [
    "English", "Chinese", "Japanese", "Korean", "Hindi", "Spanish",
    "Portuguese", "French", "German", "Arabic", "Russian", "Custom",
]
_DATA_VENDORS = {
    "core_stock_apis": ["yfinance", "alpha_vantage"],
    "technical_indicators": ["yfinance", "alpha_vantage"],
    "fundamental_data": ["yfinance", "alpha_vantage"],
    "news_data": ["yfinance", "alpha_vantage"],
    "macro_data": ["fred"],
    "prediction_markets": ["polymarket"],
}
_DATA_KEYS = {"fred": "FRED_API_KEY", "alpha_vantage": "ALPHA_VANTAGE_API_KEY"}


def _models(provider: str, mode: str) -> list[dict[str, str]]:
    from tradingagents.llm_clients.model_catalog import get_model_options

    try:
        opts = get_model_options(provider, mode)
    except Exception:  # noqa: BLE001 - native providers have no catalog entry
        return []
    out = []
    for opt in opts:
        if isinstance(opt, (tuple, list)) and len(opt) == 2:
            out.append({"label": opt[0], "model_id": opt[1]})
        else:
            out.append({"label": str(opt), "model_id": str(opt)})
    return out


def build_capabilities() -> dict[str, Any]:
    from tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV
    from tradingagents.llm_clients.capabilities import get_capabilities
    from tradingagents.llm_clients.model_catalog import get_known_models
    from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS

    providers = []
    for name, key_env in PROVIDER_API_KEY_ENV.items():
        spec = OPENAI_COMPATIBLE_PROVIDERS.get(name)
        providers.append(
            {
                "name": name,
                "api_key_env": key_env,
                "native": name in _NATIVE,
                "base_url": getattr(spec, "base_url", None) if spec else None,
                "base_url_env": getattr(spec, "base_url_env", None) if spec else None,
                "key_optional": getattr(spec, "key_optional", False) if spec else (key_env is None),
                "require_base_url": getattr(spec, "require_base_url", False) if spec else False,
                "quick_models": _models(name, "quick"),
                "deep_models": _models(name, "deep"),
            }
        )

    capabilities = {}
    try:
        for _provider, model_ids in get_known_models().items():
            for model_id in model_ids:
                try:
                    capabilities[model_id] = dataclasses.asdict(get_capabilities(model_id))
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        pass

    return {
        "schema": "capabilities",
        "providers": providers,
        "model_capabilities": capabilities,
        "reasoning_knobs": _REASONING_KNOBS,
        "output_languages": _OUTPUT_LANGUAGES,
        "data_vendors": _DATA_VENDORS,
        "data_keys": _DATA_KEYS,
    }


def capabilities_command(emitter: Emitter) -> int:
    emitter.write_object(build_capabilities())
    return 0
