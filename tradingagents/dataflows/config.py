from copy import deepcopy
from typing import Dict, Optional

import tradingagents.default_config as default_config

# Use default config but allow it to be overridden
_config: Optional[Dict] = None


def initialize_config() -> None:
    """Initialize the configuration with default values. Thread-safe."""
    global _config
    if _config is None:
        _config = deepcopy(default_config.DEFAULT_CONFIG)


def set_config(config: Dict):
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


def get_config() -> Dict:
    """Get the current configuration as a reference.
    
    WARNING: This returns a reference to the internal config dict, not a copy.
    Modifications will affect the global config. Use set_config() for safe updates.
    
    Returns:
        Reference to the current configuration dictionary
    """
    if _config is None:
        initialize_config()
    return _config.copy()


# Initialize with default config
initialize_config()
