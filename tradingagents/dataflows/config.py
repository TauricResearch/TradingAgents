from contextvars import ContextVar
from copy import deepcopy

import tradingagents.default_config as default_config

# Use default config but allow it to be overridden
_config: dict | None = None

# Config set for the current execution context. ``TradingAgentsGraph`` calls
# ``set_config`` when it is built, and data tools read the config at call time
# through ``get_config`` — so with several graphs alive in one process (vendor
# comparisons, config sweeps), the config has to travel with the run instead of
# being a single process-wide dict. LangGraph copies the caller's context into
# its tool workers, so tool calls resolve to the graph that started the run.
_config_var: ContextVar[dict | None] = ContextVar("tradingagents_config", default=None)


def initialize_config():
    """Initialize the configuration with default values."""
    global _config
    if _config is None:
        _config = deepcopy(default_config.DEFAULT_CONFIG)


def _merge_config(base: dict, incoming: dict) -> dict:
    """Merge ``incoming`` into ``base`` and return ``base``.

    Dict-valued keys are merged one level deep; scalar keys are replaced.
    """
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key].update(value)
        else:
            base[key] = value
    return base


def set_config(config: dict):
    """Update the configuration with custom values.

    A config carrying every ``DEFAULT_CONFIG`` key (what
    ``TradingAgentsGraph(config=...)`` passes) rebuilds the active config from
    ``DEFAULT_CONFIG``, so vendor overrides set by an earlier graph cannot leak
    into one built with the defaults. A partial dict keeps the documented
    merge: dict-valued keys (e.g. ``data_vendors``) are merged one level deep
    so ``{"data_vendors": {"core_stock_apis": "alpha_vantage"}}`` keeps the
    other nested keys; scalar keys are replaced.

    The result is recorded for the current execution context (read first by
    ``get_config``) and, as before, for the process.
    """
    global _config
    incoming = deepcopy(config)
    if all(key in incoming for key in default_config.DEFAULT_CONFIG):
        active = _merge_config(deepcopy(default_config.DEFAULT_CONFIG), incoming)
    else:
        initialize_config()
        active = _merge_config(deepcopy(_config), incoming)
    _config = deepcopy(active)
    _config_var.set(active)


def get_config() -> dict:
    """Get the current configuration.

    The config set for the current execution context takes precedence over the
    process-wide one, so concurrent runs with different configs each read
    their own.
    """
    var_value = _config_var.get()
    if var_value is not None:
        return deepcopy(var_value)
    if _config is None:
        initialize_config()
    return deepcopy(_config)


# Initialize with default config
initialize_config()
