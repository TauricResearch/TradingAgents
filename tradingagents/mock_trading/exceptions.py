"""Custom exceptions for mock trading system."""

class MockTradingError(Exception):
    """Base exception class for mock trading system."""
    pass


class InsufficientFundsError(MockTradingError):
    """Raised when a portfolio has insufficient cash to execute a trade."""
    pass


class PositionNotFoundError(MockTradingError):
    """Raised when attempting to sell a stock symbol that is not currently held."""
    pass


class MarketDataUnavailableError(MockTradingError):
    """Raised when yfinance or real-time data queries fail or return empty datasets."""
    pass


class InvalidTickerError(MockTradingError):
    """Raised when a stock ticker semantically fails symbol format validation rules."""
    pass
