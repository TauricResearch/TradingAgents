"""
Backwards compatibility layer for dataflows config.
This module now uses the centralized configuration system.
"""
from tradingagents.config import (
    get_config as _get_config,
    update_config as _update_config,
    get_config_value
)
from typing import Dict, Optional

# For backwards compatibility
DATA_DIR: Optional[str] = None


def initialize_config():
    """Initialize the configuration with default values."""
    global DATA_DIR
    config = _get_config()
    DATA_DIR = config.get("data_dir")


def set_config(config: Dict):
    """Update the configuration with custom values."""
    global DATA_DIR
    _update_config(config)
    updated_config = _get_config()
    DATA_DIR = updated_config.get("data_dir")


def get_config() -> Dict:
    """Get the current configuration."""
    return _get_config()


# Initialize with default config
initialize_config()
