from copy import deepcopy

import tradingagents.default_config as default_config

# Use default config but allow it to be overridden. Kept None until first
# get_config()/set_config()/initialize_config() so importing this module
# (e.g. during pytest collection) does not eagerly materialize config (#194).
_config: dict | None = None


def initialize_config():
    """Initialize the configuration with default values."""
    global _config
    if _config is None:
        _config = deepcopy(default_config.DEFAULT_CONFIG)


def set_config(config: dict):
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


def get_config() -> dict:
    """Get the current configuration."""
    if _config is None:
        initialize_config()
    return deepcopy(_config)
