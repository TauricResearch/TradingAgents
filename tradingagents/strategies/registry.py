"""Strategy registry with auto-discovery, signal computation, and role-based formatting."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .base import BaseStrategy, Role, StrategySignal

logger = logging.getLogger(__name__)

_MAX_WORKERS = 4  # cap threads; strategies do network I/O, not CPU work

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


def _run_strategy(
    strategy: BaseStrategy, ticker: str, date: str, context: dict[str, Any] | None,
) -> StrategySignal | None:
    """Execute a single strategy, returning None on failure."""
    try:
        return strategy.compute(ticker, date, context)
    except Exception:
        logger.warning("Strategy %s failed for %s@%s", strategy.name, ticker, date, exc_info=True)
        return None


def compute_signals(
    ticker: str, date: str, context: dict[str, Any] | None = None
) -> list[StrategySignal]:
    """Run every registered strategy in parallel and collect non-None signals."""
    _discover()
    signals: list[StrategySignal] = []
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(_registry) or 1)) as pool:
        futures = {
            pool.submit(_run_strategy, s, ticker, date, context): s
            for s in _registry
        }
        for fut in as_completed(futures):
            sig = fut.result()
            if sig is not None:
                signals.append(sig)
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
