from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from copy import deepcopy

import tradingagents.default_config as default_config

# Use default config but allow it to be overridden
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


def replace_config(config: Mapping) -> None:
    """Replace the process-global configuration with an exact deep copy."""
    global _config
    _config = deepcopy(dict(config))


@contextmanager
def config_scope(config: Mapping) -> Iterator[None]:
    """Install one run's config and restore the exact previous mapping."""
    previous = get_config()
    replace_config(config)
    try:
        yield
    finally:
        replace_config(previous)


def get_config() -> dict:
    """Get the current configuration."""
    if _config is None:
        initialize_config()
    return deepcopy(_config)


# Initialize with default config
initialize_config()
