from copy import deepcopy
from typing import Any, Dict, Optional

import tradingagents.default_config as default_config

# Use default config but allow it to be overridden
_config: Optional[Dict] = None


def initialize_config():
    """Initialize the configuration with default values."""
    global _config
    if _config is None:
        _config = deepcopy(default_config.DEFAULT_CONFIG)


def _deep_merge_dicts(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def set_config(config: Dict):
    """Update the configuration with custom values."""
    global _config
    if _config is None:
        _config = deepcopy(default_config.DEFAULT_CONFIG)
    _config = _deep_merge_dicts(_config, config)


def get_config() -> Dict:
    """Get the current configuration."""
    if _config is None:
        initialize_config()
    return deepcopy(_config)


# Initialize with default config
initialize_config()
