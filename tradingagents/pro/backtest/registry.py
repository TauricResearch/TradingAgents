"""Strategy registry (roadmap P0.2 / architecture track T1).

A tiny in-process registry mapping a stable ``strategy_id`` to a factory that
builds a configured ``Strategy`` from a resolved parameter dict. No
entry-points / plugin-loading magic — strategies register by importing their
module, which keeps discovery deterministic and auditable (consistent with
the repo's "agents as configuration" ADR-0014). This is what the engine
(P0.4) and the ``GET /api/backtest/strategies`` endpoint (P0.6) build on.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tradingagents.pro.backtest.strategy import ParamSpace, Strategy

# strategy_id -> (factory, param_space, description)
_REGISTRY: dict[str, tuple[Callable[[dict[str, Any]], Strategy], ParamSpace, str]] = {}


@dataclass(frozen=True)
class StrategyInfo:
    """Serializable description of a registered strategy (for the API/UI)."""

    id: str
    description: str
    params: list[dict[str, Any]]


def register(
    strategy_id: str, params: ParamSpace, description: str = ""
) -> Callable[[Callable[[dict[str, Any]], Strategy]], Callable[[dict[str, Any]], Strategy]]:
    """Decorator registering a strategy factory under ``strategy_id``.

    The decorated callable takes a resolved parameter dict and returns a
    ``Strategy``. ``params`` is the declared space (used to validate overrides
    and to advertise the schema). Re-registering the same id raises — ids are
    stable identifiers, not to be silently shadowed.
    """

    def deco(factory: Callable[[dict[str, Any]], Strategy]):
        if strategy_id in _REGISTRY:
            raise ValueError(f"strategy id {strategy_id!r} already registered")
        _REGISTRY[strategy_id] = (factory, params, description)
        return factory

    return deco


def build_strategy(strategy_id: str, params: dict[str, Any] | None = None) -> Strategy:
    """Instantiate a registered strategy with ``params`` merged onto its
    declared defaults. Raises ValueError (→ API 422) for an unknown id or an
    out-of-domain parameter (delegated to ``ParamSpace.resolve``)."""
    if strategy_id not in _REGISTRY:
        raise ValueError(
            f"unknown strategy {strategy_id!r}; "
            f"registered: {sorted(_REGISTRY)}")
    factory, space, _ = _REGISTRY[strategy_id]
    resolved = space.resolve(params)
    return factory(resolved)


def list_strategies() -> list[StrategyInfo]:
    """Every registered strategy, id-sorted, for discovery (P0.6)."""
    return [
        StrategyInfo(id=sid, description=desc, params=space.schema())
        for sid, (_factory, space, desc) in sorted(_REGISTRY.items())
    ]


def is_registered(strategy_id: str) -> bool:
    return strategy_id in _REGISTRY


def _clear_registry() -> None:
    """Test-only: drop all registrations (keeps tests hermetic)."""
    _REGISTRY.clear()


__all__ = [
    "StrategyInfo",
    "build_strategy",
    "is_registered",
    "list_strategies",
    "register",
]
