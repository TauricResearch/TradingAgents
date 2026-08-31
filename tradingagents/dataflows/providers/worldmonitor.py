"""
WorldMonitor data provider.

Provides macro-economic and geopolitical data from 500+ feeds
via WorldMonitor MCP server.
"""

from datetime import datetime
from typing import Optional

import pandas as pd

from .base import DataProvider
from .worldmonitor_mcp import get_worldmonitor_client


class WorldMonitorProvider(DataProvider):
    """WorldMonitor provider for macro/geopolitical data."""

    @property
    def name(self) -> str:
        return "worldmonitor"

    @property
    def supported_markets(self) -> list[str]:
        return ["GLOBAL"]

    def get_ohlcv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
    ) -> Optional[pd.DataFrame]:
        """WorldMonitor doesn't provide OHLCV data."""
        return None

    def get_fundamentals(self, symbol: str) -> Optional[dict]:
        """WorldMonitor doesn't provide company fundamentals."""
        return None

    def get_financial_statement(
        self,
        symbol: str,
        statement_type: str,
        freq: str = "quarterly",
    ) -> Optional[pd.DataFrame]:
        """WorldMonitor doesn't provide financial statements."""
        return None

    def get_macro_indicators(self, country: str = "US") -> Optional[dict]:
        """
        Fetch macro-economic indicators from WorldMonitor.

        Returns:
            Dict with GDP, inflation, unemployment, interest rates, etc.
        """
        try:
            client = get_worldmonitor_client()
            data = client.get_economic_data(country=country)
            return data
        except Exception as e:
            print(f"Error fetching macro indicators from WorldMonitor: {e}")
            return None

    def get_geopolitical_risk(
        self,
        country: str | None = None,
    ) -> Optional[dict]:
        """
        Fetch geopolitical risk assessment from WorldMonitor.

        Args:
            country: Optional country code for specific risk

        Returns:
            Dict with risk indices, conflict monitoring, etc.
        """
        try:
            client = get_worldmonitor_client()

            if country:
                data = client.get_country_risk(country=country)
            else:
                data = client.get_world_brief()

            return data
        except Exception as e:
            print(f"Error fetching geopolitical risk from WorldMonitor: {e}")
            return None

    def get_news_sentiment(
        self,
        query: str,
        lookback_days: int = 7,
    ) -> Optional[dict]:
        """
        Fetch news with sentiment analysis from WorldMonitor.

        Args:
            query: Search query
            lookback_days: Not used (WorldMonitor handles freshness)

        Returns:
            Dict with news intelligence
        """
        try:
            client = get_worldmonitor_client()
            data = client.get_news_intelligence(query=query)
            return data
        except Exception as e:
            print(f"Error fetching news sentiment from WorldMonitor: {e}")
            return None

    def get_conflict_events(self) -> Optional[dict]:
        """
        Fetch conflict events from WorldMonitor.

        Returns:
            Dict with conflict events
        """
        try:
            client = get_worldmonitor_client()
            data = client.get_conflict_events()
            return data
        except Exception as e:
            print(f"Error fetching conflict events from WorldMonitor: {e}")
            return None

    def get_prediction_markets(self) -> Optional[dict]:
        """
        Fetch prediction markets from WorldMonitor.

        Returns:
            Dict with prediction markets
        """
        try:
            client = get_worldmonitor_client()
            data = client.get_prediction_markets()
            return data
        except Exception as e:
            print(f"Error fetching prediction markets from WorldMonitor: {e}")
            return None

    def get_energy_data(self) -> Optional[dict]:
        """
        Fetch energy data from WorldMonitor.

        Returns:
            Dict with energy data
        """
        try:
            client = get_worldmonitor_client()
            data = client.get_energy_data()
            return data
        except Exception as e:
            print(f"Error fetching energy data from WorldMonitor: {e}")
            return None

    def get_chokepoint_status(self) -> Optional[dict]:
        """
        Fetch maritime chokepoint status from WorldMonitor.

        Returns:
            Dict with chokepoint status
        """
        try:
            client = get_worldmonitor_client()
            data = client.get_chokepoint_status()
            return data
        except Exception as e:
            print(f"Error fetching chokepoint status from WorldMonitor: {e}")
            return None

    def get_forecast_predictions(self) -> Optional[dict]:
        """
        Fetch AI forecast predictions from WorldMonitor.

        Returns:
            Dict with forecast predictions
        """
        try:
            client = get_worldmonitor_client()
            data = client.get_forecast_predictions()
            return data
        except Exception as e:
            print(f"Error fetching forecast predictions from WorldMonitor: {e}")
            return None
