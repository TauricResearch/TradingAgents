"""Strategy registry with auto-discovery, signal computation, and role-based formatting."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Any

from .base import BaseStrategy, Role, StrategySignal

logger = logging.getLogger(__name__)

_registry: list[BaseStrategy] = []


def _discover() -> None:
    """Auto-discover BaseStrategy subclasses in this package."""
    if _registry:
        return
    import tradingagents.strategies as pkg

    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name in ("base", "registry", "scorecard", "__init__"):
            continue
        try:
            mod = importlib.import_module(f"{pkg.__name__}.{info.name}")
        except Exception:
            logger.warning("Failed to import strategy module %s", info.name, exc_info=True)
            continue
        for attr in vars(mod).values():
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseStrategy)
                and attr is not BaseStrategy
                and attr.name
            ):
                _registry.append(attr())


def get_registry() -> list[BaseStrategy]:
    """Return all registered strategy instances."""
    _discover()
    return list(_registry)


def reset_registry() -> None:
    """Clear the registry (useful for testing)."""
    _registry.clear()


def compute_signals(
    ticker: str, date: str, context: dict[str, Any] | None = None
) -> list[StrategySignal]:
    """Run every registered strategy and collect non-None signals."""
    _discover()
    signals: list[StrategySignal] = []
    for strategy in _registry:
        try:
            sig = strategy.compute(ticker, date, context)
            if sig is not None:
                signals.append(sig)
        except Exception:
            logger.warning("Strategy %s failed for %s@%s", strategy.name, ticker, date, exc_info=True)
    return signals


def format_signals_for_role(signals: list[StrategySignal], role: Role) -> str:
    """Format signals relevant to *role* as a prompt section.

    Returns an empty string when no signals match the role.
    """
    _discover()
    # Build a set of strategy names relevant to this role
    role_names: set[str] = set()
    for s in _registry:
        if role in s.roles:
            role_names.add(s.name)

    relevant = [s for s in signals if s["name"] in role_names]
    if not relevant:
        return ""

    lines = ["## Quantitative Strategy Signals"]
    for s in relevant:
        strength = f"{s['signal_strength']:+.2f}"
        lines.append(f"- **{s['name']}** [{s['direction']}, {strength}]: {s['detail']}")
    return "\n".join(lines)
