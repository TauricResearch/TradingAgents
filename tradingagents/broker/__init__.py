"""Broker abstraction: execute orders behind a swappable adapter.

The wiki decision is broker interchangeability via an adapter: one internal
interface, concrete brokers behind it (Alpaca for the MVP paper trading, IBKR
for production). ``PaperBroker`` is an in-process simulator for tests and local
paper runs; ``AlpacaBroker`` talks to Alpaca's paper REST API.

Orders are idempotent on ``client_order_id`` (anti double-order), which is also
what reconciliation uses after a crash (broker = source of truth).
"""

from .base import Broker, BrokerOrder, OrderRequest, OrderStatus
from .paper import PaperBroker
from .commission import (
    CommissionModel,
    PercentCommission,
    PerShareCommission,
    PerTradeCommission,
    ZeroCommission,
)

__all__ = [
    "Broker",
    "BrokerOrder",
    "OrderRequest",
    "OrderStatus",
    "PaperBroker",
    "CommissionModel",
    "ZeroCommission",
    "PerTradeCommission",
    "PerShareCommission",
    "PercentCommission",
]
