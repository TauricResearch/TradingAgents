from copy import deepcopy
import tradingagents.default_config as default_config
from typing import Dict, Optional

# Use default config but allow it to be overridden
_config: Optional[Dict] = None


def _deep_merge_dicts(base: Dict, override: Dict) -> Dict:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def initialize_config():
    """Initialize the configuration with default values."""
    global _config
    if _config is None:
        _config = default_config.normalize_llm_routing(default_config.DEFAULT_CONFIG)


def set_config(config: Dict):
    """Update the configuration with custom values."""
    global _config
    _config = default_config.normalize_llm_routing(
        _deep_merge_dicts(default_config.DEFAULT_CONFIG, config)
    )


def get_config() -> Dict:
    """Get the current configuration."""
    if _config is None:
        initialize_config()
    return default_config.normalize_llm_routing(_config)


# Initialize with default config
initialize_config()
