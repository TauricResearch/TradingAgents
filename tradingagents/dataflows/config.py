"""Backwards-compatible shim around tradingagents.runtime.

New code should import from ``tradingagents.runtime`` directly.  This
module exists so existing callers keep working without an immediate
rewrite.  Both surfaces share state because they delegate to the same
ContextVar/lock in ``runtime``.
"""

from typing import Dict

from tradingagents.runtime import (
    get_runtime_config as _get_runtime_config,
    set_runtime_config as _set_runtime_config,
)


def initialize_config() -> None:
    """No-op kept for backwards compatibility.

    The runtime config is initialized at module import time in
    ``tradingagents.runtime``; explicit initialization is no longer needed.
    """
    return None


def set_config(config: Dict) -> None:
    """Update the process-wide default config.

    Equivalent to ``set_runtime_config(config, scope='default')``.
    """
    _set_runtime_config(config, scope="default")


def get_config() -> Dict:
    """Return a copy of the current effective configuration."""
    return _get_runtime_config()
