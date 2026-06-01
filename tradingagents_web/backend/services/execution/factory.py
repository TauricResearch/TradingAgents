"""
Trader factory — maps (mode, broker) → BaseTraderInterface subclass.

To add a new broker:
  1. Create a new class in services/execution/ that inherits BaseTraderInterface
  2. Add it to _REGISTRY with a unique broker key
  3. No other files need to change.
"""
from .base import BaseTraderInterface
from .simulation import SimulationTrader

_REGISTRY: dict[str, type[BaseTraderInterface]] = {
    "simulation": SimulationTrader,
    # Future real brokers:
    # "binance": BinanceTrader,
    # "midas": MidasTrader,
    # "ibkr": IBKRTrader,
}


def get_trader(
    mode: str,
    broker: str,
    portfolio_id: int = 1,
    initial_capital: float = 100_000.0,
    db=None,
) -> BaseTraderInterface:
    """
    Returns the appropriate trader implementation.

    In simulation mode, always returns SimulationTrader regardless of broker.
    In live mode, looks up the broker in the registry.
    """
    key = "simulation" if mode == "simulation" else broker
    cls = _REGISTRY.get(key)
    if cls is None:
        raise ValueError(
            f"No trader implementation for mode={mode!r} broker={broker!r}. "
            f"Available: {list(_REGISTRY.keys())}"
        )
    return cls(portfolio_id=portfolio_id, initial_capital=initial_capital, db=db)


def list_available_brokers() -> list[str]:
    return list(_REGISTRY.keys())
