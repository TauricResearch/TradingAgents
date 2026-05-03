from contextvars import ContextVar
from typing import Dict

import tradingagents.default_config as default_config

_config_var: ContextVar[dict | None] = ContextVar("tradingagents_config", default=None)


def initialize_config():
    """Initialize the configuration with default values."""
    if _config_var.get() is None:
        _config_var.set(default_config.DEFAULT_CONFIG.copy())


def set_config(config: Dict):
    """Set configuration for the current context."""
    base = default_config.DEFAULT_CONFIG.copy()
    base.update(config)
    _config_var.set(base)


def get_config() -> Dict:
    """Get the current configuration."""
    cfg = _config_var.get()
    if cfg is None:
        cfg = default_config.DEFAULT_CONFIG.copy()
        _config_var.set(cfg)
    return cfg.copy()


def use_config(config: Dict):
    """Apply configuration to the current context and return a reset token."""
    base = default_config.DEFAULT_CONFIG.copy()
    base.update(config)
    return _config_var.set(base)


def reset_config(token) -> None:
    """Restore the configuration context represented by ``token``."""
    _config_var.reset(token)


# Initialize with default config
initialize_config()
