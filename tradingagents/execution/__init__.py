"""Execution module for broker integrations and order management.

This module provides a unified interface for interacting with various brokers
(Alpaca, IBKR, Paper) and managing order execution.

Issue #22: [EXEC-21] Broker base interface - abstract broker class
Issue #23: [EXEC-22] Broker router - route by asset class

Submodules:
    broker_base: Abstract base class for broker implementations
    broker_router: Router for multi-broker setups

Classes:
    Enums:
    - AssetClass: Supported asset classes (EQUITY, ETF, CRYPTO, etc.)
    - OrderSide: Order side (BUY, SELL)
    - OrderType: Order types (MARKET, LIMIT, STOP, etc.)
    - TimeInForce: Order duration (DAY, GTC, IOC, etc.)
    - OrderStatus: Order execution status
    - PositionSide: Position side (LONG, SHORT)

    Data Classes:
    - OrderRequest: Request to submit an order
    - Order: Order information returned from broker
    - Position: Current position in an asset
    - AccountInfo: Broker account information
    - Quote: Current quote/price data
    - AssetInfo: Asset/instrument information

    Exceptions:
    - BrokerError: Base exception for broker errors
    - ConnectionError: Error connecting to broker
    - AuthenticationError: Authentication failed
    - OrderError: Error submitting or managing order
    - InsufficientFundsError: Insufficient funds for order
    - InvalidOrderError: Invalid order parameters
    - PositionError: Error with position operations
    - RateLimitError: Rate limit exceeded

    Abstract Base Class:
    - BrokerBase: Abstract base class for broker implementations

Example:
    >>> from tradingagents.execution import (
    ...     BrokerBase,
    ...     OrderRequest,
    ...     OrderSide,
    ...     OrderType,
    ... )
    >>>
    >>> # Create a market buy order
    >>> order_request = OrderRequest.market("AAPL", OrderSide.BUY, 100)
    >>>
    >>> # Or with more options
    >>> order_request = OrderRequest.limit(
    ...     symbol="AAPL",
    ...     side=OrderSide.BUY,
    ...     quantity=100,
    ...     limit_price=150.00,
    ... )
"""

from .broker_base import (
    # Enums
    AssetClass,
    OrderSide,
    OrderType,
    TimeInForce,
    OrderStatus,
    PositionSide,
    # Data Classes
    OrderRequest,
    Order,
    Position,
    AccountInfo,
    Quote,
    AssetInfo,
    # Exceptions
    BrokerError,
    ConnectionError,
    AuthenticationError,
    OrderError,
    InsufficientFundsError,
    InvalidOrderError,
    PositionError,
    RateLimitError,
    # Abstract Base Class
    BrokerBase,
)

from .broker_router import (
    # Router Classes
    BrokerRouter,
    BrokerRegistration,
    RoutingDecision,
    SymbolClassifier,
    # Router Exceptions
    RoutingError,
    NoBrokerError,
    BrokerNotFoundError,
    DuplicateBrokerError,
)

from .alpaca_broker import (
    AlpacaBroker,
    ALPACA_AVAILABLE,
)

from .ibkr_broker import (
    IBKRBroker,
    IB_INSYNC_AVAILABLE,
    FUTURES_SPECS,
)

from .paper_broker import PaperBroker

__all__ = [
    # Enums
    "AssetClass",
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "OrderStatus",
    "PositionSide",
    # Data Classes
    "OrderRequest",
    "Order",
    "Position",
    "AccountInfo",
    "Quote",
    "AssetInfo",
    # Exceptions
    "BrokerError",
    "ConnectionError",
    "AuthenticationError",
    "OrderError",
    "InsufficientFundsError",
    "InvalidOrderError",
    "PositionError",
    "RateLimitError",
    # Abstract Base Class
    "BrokerBase",
    # Router
    "BrokerRouter",
    "BrokerRegistration",
    "RoutingDecision",
    "SymbolClassifier",
    "RoutingError",
    "NoBrokerError",
    "BrokerNotFoundError",
    "DuplicateBrokerError",
    # Alpaca Broker
    "AlpacaBroker",
    "ALPACA_AVAILABLE",
    # IBKR Broker
    "IBKRBroker",
    "IB_INSYNC_AVAILABLE",
    "FUTURES_SPECS",
    # Paper Broker
    "PaperBroker",
]
