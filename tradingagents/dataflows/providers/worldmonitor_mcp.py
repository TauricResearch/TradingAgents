"""
WorldMonitor MCP Client.

Connects to WorldMonitor's MCP server for macro-economic and
geopolitical intelligence data.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Optional

import httpx


class WorldMonitorMCPClient:
    """Client for WorldMonitor MCP server."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://worldmonitor.app/mcp",
    ):
        """
        Initialize WorldMonitor MCP client.

        Args:
            api_key: WorldMonitor API key (wm_...). If not provided,
                    reads from WORLDMONITOR_API_KEY env var.
            base_url: MCP server URL.
        """
        self.api_key = api_key or os.environ.get("WORLDMONITOR_API_KEY")
        self.base_url = base_url
        self._session: httpx.Client | None = None

    @property
    def headers(self) -> dict[str, str]:
        """Get request headers."""
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["X-WorldMonitor-Key"] = self.api_key
        return headers

    def _get_session(self) -> httpx.Client:
        """Get or create HTTP session."""
        if self._session is None or self._session.is_closed:
            self._session = httpx.Client(timeout=30.0)
        return self._session

    def _call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Call an MCP tool.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool response data
        """
        session = self._get_session()

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {},
            },
        }

        response = session.post(
            self.base_url,
            headers=self.headers,
            json=payload,
        )
        response.raise_for_status()

        result = response.json()
        if "error" in result:
            raise Exception(f"MCP error: {result['error']}")

        return result.get("result", {})

    def list_tools(self) -> list[dict[str, Any]]:
        """List available MCP tools."""
        session = self._get_session()

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
        }

        response = session.post(
            self.base_url,
            headers=self.headers,
            json=payload,
        )
        response.raise_for_status()

        result = response.json()
        return result.get("result", {}).get("tools", [])

    # -----------------------------------------------------------------------
    # Market & Economic Data
    # -----------------------------------------------------------------------

    def get_market_data(
        self,
        jmespath: str | None = None,
    ) -> dict[str, Any]:
        """
        Get market data (stocks, forex, commodities).

        Args:
            jmespath: Optional JMESPath projection for response filtering

        Returns:
            Market data
        """
        args = {}
        if jmespath:
            args["jmespath"] = jmespath
        return self._call_tool("get_market_data", args)

    def get_economic_data(
        self,
        country: str = "US",
        jmespath: str | None = None,
    ) -> dict[str, Any]:
        """
        Get economic indicators.

        Args:
            country: Country code (ISO 3166-1 alpha-3)
            jmespath: Optional JMESPath projection

        Returns:
            Economic data
        """
        args = {"country": country}
        if jmespath:
            args["jmespath"] = jmespath
        return self._call_tool("get_economic_data", args)

    def get_prediction_markets(
        self,
        jmespath: str | None = None,
    ) -> dict[str, Any]:
        """
        Get prediction markets data.

        Args:
            jmespath: Optional JMESPath projection

        Returns:
            Prediction markets data
        """
        args = {}
        if jmespath:
            args["jmespath"] = jmespath
        return self._call_tool("get_prediction_markets", args)

    # -----------------------------------------------------------------------
    # Geopolitical & Conflict Data
    # -----------------------------------------------------------------------

    def get_world_brief(
        self,
        jmespath: str | None = None,
    ) -> dict[str, Any]:
        """
        Get world brief summary.

        Args:
            jmespath: Optional JMESPath projection

        Returns:
            World brief
        """
        args = {}
        if jmespath:
            args["jmespath"] = jmespath
        return self._call_tool("get_world_brief", args)

    def get_country_brief(
        self,
        country: str,
        jmespath: str | None = None,
    ) -> dict[str, Any]:
        """
        Get country brief.

        Args:
            country: Country code (ISO 3166-1 alpha-3)
            jmespath: Optional JMESPath projection

        Returns:
            Country brief
        """
        args = {"country": country}
        if jmespath:
            args["jmespath"] = jmespath
        return self._call_tool("get_country_brief", args)

    def get_country_risk(
        self,
        country: str,
        jmespath: str | None = None,
    ) -> dict[str, Any]:
        """
        Get country risk assessment.

        Args:
            country: Country code (ISO 3166-1 alpha-3)
            jmespath: Optional JMESPath projection

        Returns:
            Country risk data
        """
        args = {"country": country}
        if jmespath:
            args["jmespath"] = jmespath
        return self._call_tool("get_country_risk", args)

    def get_conflict_events(
        self,
        jmespath: str | None = None,
    ) -> dict[str, Any]:
        """
        Get conflict events.

        Args:
            jmespath: Optional JMESPath projection

        Returns:
            Conflict events
        """
        args = {}
        if jmespath:
            args["jmespath"] = jmespath
        return self._call_tool("get_conflict_events", args)

    # -----------------------------------------------------------------------
    # News & Intelligence
    # -----------------------------------------------------------------------

    def get_news_intelligence(
        self,
        query: str | None = None,
        jmespath: str | None = None,
    ) -> dict[str, Any]:
        """
        Get news intelligence.

        Args:
            query: Optional search query
            jmespath: Optional JMESPath projection

        Returns:
            News intelligence
        """
        args = {}
        if query:
            args["query"] = query
        if jmespath:
            args["jmespath"] = jmespath
        return self._call_tool("get_news_intelligence", args)

    # -----------------------------------------------------------------------
    # Energy & Commodities
    # -----------------------------------------------------------------------

    def get_energy_data(
        self,
        jmespath: str | None = None,
    ) -> dict[str, Any]:
        """
        Get energy data.

        Args:
            jmespath: Optional JMESPath projection

        Returns:
            Energy data
        """
        args = {}
        if jmespath:
            args["jmespath"] = jmespath
        return self._call_tool("get_energy_data", args)

    # -----------------------------------------------------------------------
    # Maritime & Aviation
    # -----------------------------------------------------------------------

    def get_chokepoint_status(
        self,
        jmespath: str | None = None,
    ) -> dict[str, Any]:
        """
        Get maritime chokepoint status.

        Args:
            jmespath: Optional JMESPath projection

        Returns:
            Chokepoint status
        """
        args = {}
        if jmespath:
            args["jmespath"] = jmespath
        return self._call_tool("get_chokepoint_status", args)

    # -----------------------------------------------------------------------
    # Cyber Threats
    # -----------------------------------------------------------------------

    def get_cyber_threats(
        self,
        jmespath: str | None = None,
    ) -> dict[str, Any]:
        """
        Get cyber threat intelligence.

        Args:
            jmespath: Optional JMESPath projection

        Returns:
            Cyber threats
        """
        args = {}
        if jmespath:
            args["jmespath"] = jmespath
        return self._call_tool("get_cyber_threats", args)

    # -----------------------------------------------------------------------
    # Natural Disasters
    # -----------------------------------------------------------------------

    def get_natural_disasters(
        self,
        jmespath: str | None = None,
    ) -> dict[str, Any]:
        """
        Get natural disaster data.

        Args:
            jmespath: Optional JMESPath projection

        Returns:
            Natural disasters
        """
        args = {}
        if jmespath:
            args["jmespath"] = jmespath
        return self._call_tool("get_natural_disasters", args)

    # -----------------------------------------------------------------------
    # AI Forecasts
    # -----------------------------------------------------------------------

    def get_forecast_predictions(
        self,
        jmespath: str | None = None,
    ) -> dict[str, Any]:
        """
        Get AI forecast predictions.

        Args:
            jmespath: Optional JMESPath projection

        Returns:
            Forecast predictions
        """
        args = {}
        if jmespath:
            args["jmespath"] = jmespath
        return self._call_tool("get_forecast_predictions", args)

    def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.is_closed:
            self._session.close()


# Global instance
_worldmonitor_client: WorldMonitorMCPClient | None = None


def get_worldmonitor_client() -> WorldMonitorMCPClient:
    """Get or create the global WorldMonitor client."""
    global _worldmonitor_client
    if _worldmonitor_client is None:
        _worldmonitor_client = WorldMonitorMCPClient()
    return _worldmonitor_client
