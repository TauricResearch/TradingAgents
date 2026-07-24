"""Strategy SDK core types (roadmap P0 / architecture track T1).

Turns "the strategy is the LLM pipeline or its rules stand-in" into a
pluggable, parameter-declaring unit the engine, optimizer, and (later)
portfolio layer can all drive. This module defines the *contracts* only —
the protocol a strategy satisfies, the read-only context it sees per bar,
the order intents it emits, and the parameter space it declares. Wiring
into ``BacktestEngine`` (P0.4) and the registry (P0.2) build on these.

Design (docs/research/10_strategy_sdk.md, 07_lld.md T1):
- ``on_bar`` returns order *intents*, never filled orders — the broker
  decides fills on the next bar, preserving the no-look-ahead invariant.
- ``StrategyContext`` is a superset of what the engine already passes to
  ``pipeline.invoke({snapshot, equity})`` today, so strategies gain no data
  path the pipeline didn't already have.
- ``ParamSpace`` declares tunables a-priori (name, type, range) so the
  optimizer (P2) can enumerate them and every run records exactly what ran.

Plain dataclasses + ``typing.Protocol`` (no pydantic) to match the rest of
the backtest package (broker.py, engine.py) and stay import-light.
"""

from __future__ import annotations

import random
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from tradingagents.contracts import MarketSnapshot, Timeframe

# --- order intents ------------------------------------------------------------

# Order kinds a strategy may request. Only "market" is honored by the current
# SimBroker; "limit"/"stop_entry"/"stop_limit" are accepted here and become
# live when the pending-order book lands (P1/T2). Declaring them now keeps the
# intent contract stable across that change.
ORDER_KINDS = ("market", "limit", "stop_entry", "stop_limit")
ORDER_SIDES = ("BUY", "SELL")


@dataclass(frozen=True)
class BracketIntent:
    """Protective geometry to attach when an entry intent fills: a stop and a
    take-profit ladder (price, fraction-of-original), optionally trailing.
    Mirrors what ``SimBroker.open_from_recommendation`` builds today, expressed
    as an intent so the same geometry survives the move to the order book."""

    stop_loss: float
    take_profits: tuple[tuple[float, float], ...] = ()
    trailing: str | None = None  # None | "atr" | "pct" | "chandelier"
    trailing_mult: float | None = None
    trailing_period: int | None = None  # ATR/chandelier lookback (bars)


@dataclass(frozen=True)
class OrderIntent:
    """What a strategy wants done. The broker translates it into a fill next
    bar (never same-bar — no look-ahead). Exactly one of ``quantity`` or
    ``risk_pct`` sizes the order; ``risk_pct`` defers sizing to the engine's
    equity-aware sizer (the common case) while ``quantity`` is explicit."""

    kind: str  # ORDER_KINDS
    side: str  # ORDER_SIDES
    quantity: float | None = None
    risk_pct: float | None = None
    limit_price: float | None = None
    stop_price: float | None = None
    bracket: BracketIntent | None = None
    reduce_only: bool = False
    tag: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ORDER_KINDS:
            raise ValueError(f"kind must be one of {ORDER_KINDS}, got {self.kind!r}")
        if self.side not in ORDER_SIDES:
            raise ValueError(f"side must be BUY or SELL, got {self.side!r}")
        if (self.quantity is None) == (self.risk_pct is None):
            raise ValueError("exactly one of quantity or risk_pct must be set")
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.risk_pct is not None and not 0 < self.risk_pct <= 100:
            raise ValueError("risk_pct must be in (0, 100]")
        if self.kind in ("limit", "stop_limit") and self.limit_price is None:
            raise ValueError(f"{self.kind} order requires limit_price")
        if self.kind in ("stop_entry", "stop_limit") and self.stop_price is None:
            raise ValueError(f"{self.kind} order requires stop_price")


# --- read-only context a strategy sees each bar -------------------------------


@dataclass(frozen=True)
class PositionView:
    """Immutable snapshot of one open position (a strategy never mutates the
    broker directly — it emits intents)."""

    id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    stop: float
    unrealized_pnl: float
    opened_at: datetime


@dataclass(frozen=True)
class AccountView:
    equity: float
    cash_pnl: float
    gross_exposure: float
    open_positions: int


@dataclass(frozen=True)
class Fill:
    """Reported to ``on_fill`` when an intent (or a protective exit) fills."""

    order_tag: str
    symbol: str
    side: str
    quantity: float
    price: float
    at: datetime
    is_entry: bool


@dataclass(frozen=True)
class RegimeView:
    """Look-ahead-safe regime read (rule-based today; T6 may wire a learned
    classifier). Optional — None until P5.3 supplies it."""

    label: str
    confidence: float | None = None


@dataclass(frozen=True)
class StrategyContext:
    """Everything a strategy may read on a bar, assembled from the replay +
    broker. ``snapshot`` and ``equity`` are exactly today's engine inputs; the
    rest are additive and default empty so a P0 strategy needs none of the
    later-track fields."""

    snapshot: MarketSnapshot
    equity: float
    params: Mapping[str, Any]
    positions: tuple[PositionView, ...] = ()
    account: AccountView | None = None
    htf: Mapping[Timeframe, MarketSnapshot] = field(default_factory=dict)
    regime: RegimeView | None = None


# --- the strategy protocol ----------------------------------------------------


@runtime_checkable
class Strategy(Protocol):
    """A pluggable strategy. Implementations declare an ``id`` and a
    ``ParamSpace`` and react to bars by emitting ``OrderIntent``s.

    Determinism requirement: given the same context sequence and params, a
    strategy must emit the same intents (no wall-clock, no unseeded RNG in
    ``on_bar``) — the engine and optimizer rely on byte-identical replays.
    """

    id: str
    params: ParamSpace

    def on_start(self, ctx: StrategyContext) -> None:
        """Called once before the first decision bar (warm-up complete)."""

    def on_bar(self, ctx: StrategyContext) -> list[OrderIntent]:
        """React to the close of a bar; return order intents ([] == HOLD)."""

    def on_fill(self, fill: Fill) -> None:
        """Notified when one of this strategy's intents (or an exit) fills."""

    def on_stop(self, ctx: StrategyContext) -> None:
        """Called once after the last bar (end of data)."""


# --- parameter space (enables the optimizer, P2) ------------------------------

PARAM_KINDS = ("float", "int", "categorical")


@dataclass(frozen=True)
class Param:
    """One declared tunable. Numeric params use low/high(/step); categorical
    params use choices. ``default`` is the a-priori value (the shipped
    constant) — the optimizer only departs from it deliberately."""

    name: str
    kind: str
    low: float | None = None
    high: float | None = None
    step: float | None = None
    choices: tuple[Any, ...] = ()
    default: Any = None

    def __post_init__(self) -> None:
        if self.kind not in PARAM_KINDS:
            raise ValueError(f"kind must be one of {PARAM_KINDS}, got {self.kind!r}")
        if self.kind == "categorical":
            if not self.choices:
                raise ValueError(f"categorical param {self.name!r} needs choices")
            if self.default is not None and self.default not in self.choices:
                raise ValueError(
                    f"default {self.default!r} not in choices for {self.name!r}")
        else:
            if self.low is None or self.high is None:
                raise ValueError(f"numeric param {self.name!r} needs low and high")
            if self.low > self.high:
                raise ValueError(f"param {self.name!r}: low must be <= high")
            if self.step is not None and self.step <= 0:
                raise ValueError(f"param {self.name!r}: step must be positive")

    def contains(self, value: Any) -> bool:
        """Is ``value`` inside this param's declared domain?"""
        if self.kind == "categorical":
            return value in self.choices
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        if not (self.low <= value <= self.high):
            return False
        # ints must be whole numbers within the domain
        return not (self.kind == "int" and float(value) != int(value))

    def grid_values(self) -> list[Any]:
        """Enumerate this param's values for a grid search."""
        if self.kind == "categorical":
            return list(self.choices)
        if self.kind == "int":
            step = int(self.step) if self.step else 1
            return list(range(int(self.low), int(self.high) + 1, step))
        # float: needs an explicit step to enumerate (else use default only)
        if not self.step:
            return [self.default if self.default is not None else self.low]
        values, v, i = [], self.low, 0
        while v <= self.high + 1e-9:
            values.append(round(v, 10))
            i += 1
            v = self.low + i * self.step
        return values

    def sample(self, rng: random.Random) -> Any:
        if self.kind == "categorical":
            return rng.choice(self.choices)
        if self.kind == "int":
            return rng.randint(int(self.low), int(self.high))
        return rng.uniform(self.low, self.high)


class ParamSpace:
    """An ordered collection of declared params. Enumerates a grid, draws
    random samples, resolves+validates a caller-supplied override dict against
    the shipped defaults, and reports its schema for the API/UI."""

    def __init__(self, *params: Param):
        names = [p.name for p in params]
        if len(names) != len(set(names)):
            raise ValueError("duplicate param names in ParamSpace")
        self._params: tuple[Param, ...] = tuple(params)
        self._by_name: dict[str, Param] = {p.name: p for p in params}

    def __iter__(self) -> Iterator[Param]:
        return iter(self._params)

    def __len__(self) -> int:
        return len(self._params)

    def __contains__(self, name: str) -> bool:
        return name in self._by_name

    def defaults(self) -> dict[str, Any]:
        return {p.name: p.default for p in self._params}

    def resolve(self, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Merge overrides onto defaults, validating names + domains. Raises
        ValueError (→ the API maps to 422) on an unknown name or an
        out-of-range value, so a typo or bad sweep never runs silently."""
        resolved = self.defaults()
        for name, value in (overrides or {}).items():
            if name not in self._by_name:
                raise ValueError(f"unknown parameter {name!r}")
            param = self._by_name[name]
            if not param.contains(value):
                raise ValueError(
                    f"parameter {name!r} value {value!r} outside declared domain")
            resolved[name] = value
        return resolved

    def grid(self) -> Iterator[dict[str, Any]]:
        """Cartesian product of every param's grid values (P2 grid search)."""
        axes = [(p.name, p.grid_values()) for p in self._params]

        def _product(idx: int, acc: dict[str, Any]) -> Iterator[dict[str, Any]]:
            if idx == len(axes):
                yield dict(acc)
                return
            name, values = axes[idx]
            for v in values:
                acc[name] = v
                yield from _product(idx + 1, acc)

        if not axes:
            return
        yield from _product(0, {})

    def sample(self, rng: random.Random) -> dict[str, Any]:
        """One random draw from the space (P2 random/bayesian search)."""
        return {p.name: p.sample(rng) for p in self._params}

    def schema(self) -> list[dict[str, Any]]:
        """Serializable description for GET /api/backtest/strategies (P0.6)."""
        out = []
        for p in self._params:
            out.append({
                "name": p.name, "kind": p.kind,
                "low": p.low, "high": p.high, "step": p.step,
                "choices": list(p.choices), "default": p.default,
            })
        return out


__all__ = [
    "ORDER_KINDS",
    "ORDER_SIDES",
    "PARAM_KINDS",
    "AccountView",
    "BracketIntent",
    "Fill",
    "OrderIntent",
    "Param",
    "ParamSpace",
    "PositionView",
    "RegimeView",
    "Strategy",
    "StrategyContext",
]
