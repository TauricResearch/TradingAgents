from importlib import import_module

_EXPORTS = {
    "TradingAgentsGraph": "trading_graph",
    "ConditionalLogic": "conditional_logic",
    "GraphSetup": "setup",
    "Propagator": "propagation",
    "Reflector": "reflection",
    "SignalProcessor": "signal_processing",
}

__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{_EXPORTS[name]}", __name__), name)
    globals()[name] = value
    return value
