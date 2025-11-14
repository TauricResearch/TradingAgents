"""
Portfolio Management System for TradingAgents.

This package provides comprehensive portfolio management capabilities including:
- Position tracking and management
- Order execution (market, limit, stop-loss, take-profit)
- Risk management and limits
- Performance analytics
- Portfolio persistence
- Integration with TradingAgents framework

Example Usage:
    >>> from tradingagents.portfolio import Portfolio, MarketOrder
    >>> from decimal import Decimal
    >>>
    >>> # Create portfolio
    >>> portfolio = Portfolio(
    ...     initial_capital=Decimal('100000.00'),
    ...     commission=Decimal('0.001')
    ... )
    >>>
    >>> # Execute trade
    >>> order = MarketOrder('AAPL', Decimal('100'))
    >>> portfolio.execute_order(order, Decimal('150.00'))
    >>>
    >>> # Get performance metrics
    >>> metrics = portfolio.get_performance_metrics()
    >>> print(f"Sharpe Ratio: {metrics.sharpe_ratio}")
"""

# Core portfolio management
from .portfolio import Portfolio

# Position management
from .position import Position

# Order types
from .orders import (
    Order,
    MarketOrder,
    LimitOrder,
    StopLossOrder,
    TakeProfitOrder,
    OrderType,
    OrderSide,
    OrderStatus,
    create_order_from_dict,
)

# Risk management
from .risk import (
    RiskManager,
    RiskLimits,
)

# Performance analytics
from .analytics import (
    PerformanceAnalytics,
    PerformanceMetrics,
    TradeRecord,
)

# Persistence
from .persistence import PortfolioPersistence

# TradingAgents integration
from .integration import TradingAgentsPortfolioIntegration

# Exceptions
from .exceptions import (
    PortfolioException,
    InsufficientFundsError,
    InsufficientSharesError,
    InvalidOrderError,
    InvalidPositionError,
    PositionNotFoundError,
    RiskLimitExceededError,
    InvalidTickerError,
    InvalidPriceError,
    InvalidQuantityError,
    PersistenceError,
    ValidationError,
    CalculationError,
    IntegrationError,
)

__version__ = '1.0.0'

__all__ = [
    # Core
    'Portfolio',
    'Position',

    # Orders
    'Order',
    'MarketOrder',
    'LimitOrder',
    'StopLossOrder',
    'TakeProfitOrder',
    'OrderType',
    'OrderSide',
    'OrderStatus',
    'create_order_from_dict',

    # Risk
    'RiskManager',
    'RiskLimits',

    # Analytics
    'PerformanceAnalytics',
    'PerformanceMetrics',
    'TradeRecord',

    # Persistence
    'PortfolioPersistence',

    # Integration
    'TradingAgentsPortfolioIntegration',

    # Exceptions
    'PortfolioException',
    'InsufficientFundsError',
    'InsufficientSharesError',
    'InvalidOrderError',
    'InvalidPositionError',
    'PositionNotFoundError',
    'RiskLimitExceededError',
    'InvalidTickerError',
    'InvalidPriceError',
    'InvalidQuantityError',
    'PersistenceError',
    'ValidationError',
    'CalculationError',
    'IntegrationError',
]
