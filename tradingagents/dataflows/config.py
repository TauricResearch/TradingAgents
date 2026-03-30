from __future__ import annotations

from copy import deepcopy
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG, build_default_config

# Single in-process runtime config used by vendor routing.
_config: dict[str, Any] | None = None


def _base_config() -> dict[str, Any]:
    return deepcopy(DEFAULT_CONFIG)


def initialize_config() -> None:
    """Initialize runtime config once from DEFAULT_CONFIG."""
    global _config
    if _config is None:
        _config = _base_config()


def set_config(config: dict[str, Any]) -> None:
    """Merge a caller-provided config onto a fresh default baseline."""
    global _config
    base = _base_config()
    base.update(deepcopy(config))
    _config = base


def reset_config(*, load_dotenv: bool | None = None) -> None:
    """Reset runtime config to defaults.

    Args:
        load_dotenv:
            - None: reset from already-built DEFAULT_CONFIG
            - bool: rebuild defaults explicitly with/without .env
    """
    global _config
    if load_dotenv is None:
        _config = _base_config()
        return
    _config = build_default_config(load_dotenv=load_dotenv)


def get_config() -> dict[str, Any]:
    """Return an isolated copy of current runtime config."""
    if _config is None:
        initialize_config()
    return deepcopy(_config)

