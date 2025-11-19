"""
Custom exceptions for the backtesting framework.

This module defines all custom exceptions used throughout the backtesting
framework, providing clear error messages and categorization of different
failure modes.
"""


class BacktestError(Exception):
    """Base exception for all backtesting errors."""
    pass


class DataError(BacktestError):
    """Raised when there are issues with data loading or quality."""
    pass


class DataNotFoundError(DataError):
    """Raised when requested data cannot be found."""
    pass


class DataQualityError(DataError):
    """Raised when data fails quality checks."""
    pass


class DataAlignmentError(DataError):
    """Raised when data cannot be properly aligned across securities."""
    pass


class LookAheadBiasError(BacktestError):
    """Raised when look-ahead bias is detected in the backtest."""
    pass


class ExecutionError(BacktestError):
    """Raised when there are issues with order execution simulation."""
    pass


class InsufficientCapitalError(ExecutionError):
    """Raised when there is insufficient capital to execute a trade."""
    pass


class InvalidOrderError(ExecutionError):
    """Raised when an order is invalid (e.g., negative quantity)."""
    pass


class StrategyError(BacktestError):
    """Raised when there are issues with strategy execution."""
    pass


class StrategyInitializationError(StrategyError):
    """Raised when a strategy fails to initialize properly."""
    pass


class StrategyExecutionError(StrategyError):
    """Raised when a strategy encounters an error during execution."""
    pass


class ConfigurationError(BacktestError):
    """Raised when there are issues with backtest configuration."""
    pass


class InvalidConfigError(ConfigurationError):
    """Raised when configuration parameters are invalid."""
    pass


class MissingConfigError(ConfigurationError):
    """Raised when required configuration is missing."""
    pass


class PerformanceError(BacktestError):
    """Raised when there are issues computing performance metrics."""
    pass


class InsufficientDataError(PerformanceError):
    """Raised when there is insufficient data to compute metrics."""
    pass


class ReportingError(BacktestError):
    """Raised when there are issues generating reports."""
    pass


class OptimizationError(BacktestError):
    """Raised when there are issues during parameter optimization."""
    pass


class MonteCarloError(BacktestError):
    """Raised when there are issues during Monte Carlo simulation."""
    pass


class IntegrationError(BacktestError):
    """Raised when there are issues integrating with TradingAgents."""
    pass
