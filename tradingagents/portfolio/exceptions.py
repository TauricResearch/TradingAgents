"""
Custom exceptions for the portfolio management system.

This module defines all custom exceptions used throughout the portfolio
management system for clear error handling and debugging.
"""


class PortfolioException(Exception):
    """Base exception for all portfolio-related errors."""
    pass


class InsufficientFundsError(PortfolioException):
    """Raised when attempting to execute a trade with insufficient funds."""
    pass


class InsufficientSharesError(PortfolioException):
    """Raised when attempting to sell more shares than owned."""
    pass


class InvalidOrderError(PortfolioException):
    """Raised when an order is invalid or cannot be executed."""
    pass


class InvalidPositionError(PortfolioException):
    """Raised when a position is invalid or cannot be created."""
    pass


class PositionNotFoundError(PortfolioException):
    """Raised when attempting to access a position that doesn't exist."""
    pass


class RiskLimitExceededError(PortfolioException):
    """Raised when a trade would exceed risk limits."""
    pass


class InvalidTickerError(PortfolioException):
    """Raised when a ticker symbol is invalid."""
    pass


class InvalidPriceError(PortfolioException):
    """Raised when a price is invalid (negative, zero, etc.)."""
    pass


class InvalidQuantityError(PortfolioException):
    """Raised when a quantity is invalid (negative, zero, etc.)."""
    pass


class PersistenceError(PortfolioException):
    """Raised when there's an error saving or loading portfolio state."""
    pass


class ValidationError(PortfolioException):
    """Raised when input validation fails."""
    pass


class CalculationError(PortfolioException):
    """Raised when a financial calculation fails or produces invalid results."""
    pass


class IntegrationError(PortfolioException):
    """Raised when there's an error integrating with TradingAgents components."""
    pass
