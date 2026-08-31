"""
Base provider interface for the multi-source data layer.

All data providers must implement these methods to ensure
consistent data access across different markets and sources.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any

import pandas as pd
from pydantic import BaseModel, Field


class MarketData(BaseModel):
    """Standardized market data response."""
    model_config = {"arbitrary_types_allowed": True}
    
    symbol: str
    provider: str
    timestamp: datetime
    data_type: str  # "ohlcv", "fundamentals", "balance_sheet", etc.
    payload: dict | pd.DataFrame
    metadata: dict = Field(default_factory=dict)


class DataProvider(ABC):
    """Abstract base class for all data providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'yahoo', 'byma', 'worldmonitor')."""
        pass

    @property
    @abstractmethod
    def supported_markets(self) -> list[str]:
        """List of supported markets (e.g., ['US', 'AR', 'CRYPTO'])."""
        pass

    @abstractmethod
    def get_ohlcv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV (Open, High, Low, Close, Volume) data.

        Args:
            symbol: Ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Data interval (1d, 1h, etc.)

        Returns:
            DataFrame with OHLCV data or None if unavailable
        """
        pass

    @abstractmethod
    def get_fundamentals(self, symbol: str) -> Optional[dict]:
        """
        Fetch company fundamentals (PE, market cap, etc.).

        Args:
            symbol: Ticker symbol

        Returns:
            Dict with fundamental data or None if unavailable
        """
        pass

    @abstractmethod
    def get_financial_statement(
        self,
        symbol: str,
        statement_type: str,  # "balance_sheet", "income_statement", "cashflow"
        freq: str = "quarterly",
    ) -> Optional[pd.DataFrame]:
        """
        Fetch financial statements.

        Args:
            symbol: Ticker symbol
            statement_type: Type of statement
            freq: Frequency (annual or quarterly)

        Returns:
            DataFrame with financial data or None if unavailable
        """
        pass

    def has_market(self, market: str) -> bool:
        """Check if provider supports a specific market."""
        return market.upper() in [m.upper() for m in self.supported_markets]


# Aliases for backward compatibility
BaseProvider = DataProvider


class ProviderError(Exception):
    """Base exception for provider errors"""
    pass


class ProviderConnectionError(ProviderError):
    """Connection error"""
    pass


class ProviderRateLimitError(ProviderError):
    """Rate limit exceeded"""
    pass
