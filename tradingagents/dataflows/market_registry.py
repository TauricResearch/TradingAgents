"""
Market provider registry for extensible multi-market support.

Each market (VN, TH, JP, etc.) implements MarketProvider and registers
itself via the MarketRegistry. The routing layer in interface.py checks
the registry before falling back to the default US vendors.
"""

from abc import ABC, abstractmethod
import json
import os
import time
from typing import Optional


class MarketProvider(ABC):
    """Base class for market-specific data providers."""

    market_code: str = ""
    market_name: str = ""
    currency: str = ""

    @abstractmethod
    def get_listed_tickers(self) -> set:
        """Return all valid ticker symbols for this market."""
        ...

    @abstractmethod
    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> str:
        ...

    @abstractmethod
    def get_indicators(self, symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
        ...

    @abstractmethod
    def get_fundamentals(self, ticker: str, curr_date: str = None) -> str:
        ...

    @abstractmethod
    def get_balance_sheet(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        ...

    @abstractmethod
    def get_cashflow(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        ...

    @abstractmethod
    def get_income_statement(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        ...

    @abstractmethod
    def get_insider_transactions(self, ticker: str) -> str:
        ...

    @abstractmethod
    def get_news(self, ticker: str, start_date: str, end_date: str) -> str:
        ...

    @abstractmethod
    def get_global_news(self, curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
        ...

    def get_market_context(self) -> str:
        """Return market-specific context string for agent prompts."""
        return ""


# Method name -> MarketProvider method mapping
MARKET_METHOD_MAP = {
    "get_stock_data": "get_stock_data",
    "get_indicators": "get_indicators",
    "get_fundamentals": "get_fundamentals",
    "get_balance_sheet": "get_balance_sheet",
    "get_cashflow": "get_cashflow",
    "get_income_statement": "get_income_statement",
    "get_insider_transactions": "get_insider_transactions",
    "get_news": "get_news",
    "get_global_news": "get_global_news",
}


class MarketRegistry:
    """Registry of all available market providers with ticker auto-detection."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._providers = {}
            cls._instance._ticker_to_market = {}
            cls._instance._initialized = False
        return cls._instance

    def register(self, provider: MarketProvider):
        """Register a market provider."""
        self._providers[provider.market_code] = provider

    def _ensure_tickers_loaded(self):
        """Lazy-load ticker lists from all registered providers."""
        if self._initialized:
            return

        from .config import get_config
        config = get_config()
        cache_dir = config.get("data_cache_dir", "data")
        os.makedirs(cache_dir, exist_ok=True)

        for code, provider in self._providers.items():
            cache_file = os.path.join(cache_dir, f"market_tickers_{code}.json")
            tickers = None

            # Try loading from cache (24h TTL)
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, "r") as f:
                        cached = json.load(f)
                    if time.time() - cached.get("timestamp", 0) < 86400:
                        tickers = set(cached["tickers"])
                except (json.JSONDecodeError, KeyError):
                    pass

            # Fetch fresh if cache miss or expired
            if tickers is None:
                try:
                    tickers = provider.get_listed_tickers()
                    with open(cache_file, "w") as f:
                        json.dump({
                            "timestamp": time.time(),
                            "market": code,
                            "tickers": list(tickers),
                        }, f)
                except Exception as e:
                    print(f"Warning: Could not load tickers for market {code}: {e}")
                    tickers = set()

            for ticker in tickers:
                self._ticker_to_market[ticker.upper()] = code

        self._initialized = True

    def detect_market(self, ticker: str) -> Optional[str]:
        """Detect which market a ticker belongs to. Returns market code or None."""
        if not ticker:
            return None

        # Check config for explicit market override
        from .config import get_config
        config = get_config()
        market = config.get("market", "auto")
        if market not in ("auto", "US") and market in self._providers:
            return market

        self._ensure_tickers_loaded()
        return self._ticker_to_market.get(ticker.upper())

    def get_provider(self, market_code: str) -> Optional[MarketProvider]:
        """Get a market provider by its code."""
        return self._providers.get(market_code)

    def get_all_providers(self) -> dict:
        """Return all registered providers."""
        return dict(self._providers)

    def call_market_method(self, market_code: str, method: str, *args, **kwargs):
        """Call a method on the appropriate market provider."""
        provider = self.get_provider(market_code)
        if provider is None:
            raise ValueError(f"No provider registered for market '{market_code}'")

        provider_method_name = MARKET_METHOD_MAP.get(method)
        if provider_method_name is None:
            raise ValueError(f"Method '{method}' not mapped to any market provider method")

        provider_method = getattr(provider, provider_method_name)
        return provider_method(*args, **kwargs)

    @classmethod
    def reset(cls):
        """Reset the singleton (useful for testing)."""
        cls._instance = None


# Global registry instance
registry = MarketRegistry()
