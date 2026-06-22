from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType
from typing import Any

import tradingagents.default_config as default_config

# Use default config but allow it to be overridden
_config: dict[str, Any] | None = None


def _deep_freeze(mapping: dict[str, Any]) -> MappingProxyType[str, Any]:
    """Recursively freeze a dict so all nested levels are read-only.

    Lists are converted to tuples so they also become immutable.
    This avoids the cost of ``deepcopy`` on every read while guaranteeing
    that callers cannot accidentally mutate the shared configuration.
    """
    frozen: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, dict):
            frozen[key] = _deep_freeze(value)
        elif isinstance(value, list):
            frozen[key] = tuple(value)
        else:
            frozen[key] = value
    return MappingProxyType(frozen)


def initialize_config() -> None:
    """Initialize the configuration with default values."""
    global _config
    if _config is None:
        _config = deepcopy(default_config.DEFAULT_CONFIG)


def set_config(config: dict[str, Any]) -> None:
    """Update the configuration with custom values.

    Dict-valued keys (e.g. ``data_vendors``) are merged one level deep so a
    partial update like ``{"data_vendors": {"core_stock_apis": "alpha_vantage"}}``
    keeps the other nested keys from the default; scalar keys are replaced.
    """
    global _config
    initialize_config()
    incoming = deepcopy(config)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(_config.get(key), dict):
            _config[key].update(value)
        else:
            _config[key] = value


def get_config() -> MappingProxyType[str, Any]:
    """Get a read-only view of the current configuration.

    Returns a recursively frozen mapping — any attempt to modify the returned
    value (or any nested dict/list inside it) raises ``TypeError``. This is
    both safer and faster than the previous ``deepcopy``-based approach.
    """
    if _config is None:
        initialize_config()
    return _deep_freeze(_config)


# Initialize with default config
initialize_config()
