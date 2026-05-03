import tradingagents.default_config as default_config
from typing import Dict, Optional
import threading

# Use default config but allow it to be overridden
_config: Optional[Dict] = None
_config_lock = threading.Lock()


def initialize_config() -> None:
    """Initialize the configuration with default values. Thread-safe."""
    global _config
    with _config_lock:
        if _config is None:
            _config = default_config.DEFAULT_CONFIG.copy()


def set_config(config: Dict) -> None:
    """Update the configuration with custom values. Thread-safe.
    
    Args:
        config: Dictionary of configuration values to set/override
        
    Raises:
        ValueError: If config contains invalid vendor names
    """
    global _config
    with _config_lock:
        if _config is None:
            _config = default_config.DEFAULT_CONFIG.copy()
        # Validate data vendor names before merging
        if "data_vendors" in config:
            from .interface import VENDOR_METHODS
            for category, vendor in config["data_vendors"].items():
                if vendor not in VENDOR_METHODS and vendor != "default":
                    raise ValueError(
                        f"Unknown data vendor '{vendor}' for category '{category}'. "
                        f"Valid vendors: {list(VENDOR_METHODS.keys())}"
                    )
        _config.update(config)


def get_config() -> Dict:
    """Get the current configuration as a reference.
    
    WARNING: This returns a reference to the internal config dict, not a copy.
    Modifications will affect the global config. Use set_config() for safe updates.
    
    Returns:
        Reference to the current configuration dictionary
    """
    if _config is None:
        initialize_config()
    return _config


# Initialize with default config
initialize_config()
