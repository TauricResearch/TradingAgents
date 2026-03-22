"""CoinGecko data provider for DEX data.

This module provides access to CoinGecko's free API for OHLCV data and token metadata.
The output is formatted as readable text for LLM consumption.
"""

import aiohttp
from datetime import datetime
from typing import Optional

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"


class CoinGeckoProvider:
    """Async provider for CoinGecko API."""

    def __init__(self):
        self.base_url = COINGECKO_BASE_URL
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_ohlc(
        self, coin_id: str, vs_currency: str = "usd", days: int = 7
    ) -> list:
        """
        Get OHLC data for a coin.

        Args:
            coin_id: CoinGecko coin ID (e.g., 'solana', 'bitcoin')
            vs_currency: Currency to compare against (e.g., 'usd', 'eur')
            days: Number of days of data (1, 7, 14, 30, 90, 365, max)

        Returns:
            List of OHLC data points: [timestamp, open, high, low, close]
        """
        url = f"{self.base_url}/coins/{coin_id}/ohlc"
        params = {"vs_currency": vs_currency, "days": days}

        session = await self._get_session()
        async with session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.json()

    async def get_coin_data(self, coin_id: str) -> dict:
        """
        Get detailed metadata for a coin.

        Args:
            coin_id: CoinGecko coin ID (e.g., 'solana', 'bitcoin')

        Returns:
            Dictionary containing coin metadata
        """
        url = f"{self.base_url}/coins/{coin_id}"
        params = {
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false",
        }

        session = await self._get_session()
        async with session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.json()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


def _format_ohlc_data(ohlc_data: list) -> str:
    """Format OHLC data as readable text for LLM consumption."""
    if not ohlc_data:
        return "No OHLC data available."

    lines = ["OHLC Data (Open, High, Low, Close):"]
    lines.append("-" * 60)

    for point in ohlc_data:
        timestamp, open_price, high, low, close = point
        date = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"Timestamp: {date} | Open: ${open_price:,.2f} | High: ${high:,.2f} | "
            f"Low: ${low:,.2f} | Close: ${close:,.2f}"
        )

    return "\n".join(lines)


def _format_coin_info(coin_data: dict) -> str:
    """Format coin metadata as readable text for LLM consumption."""
    if not coin_data or "market_data" not in coin_data:
        return "No coin data available."

    md = coin_data.get("market_data", {})
    info = coin_data.get("info", {})

    name = coin_data.get("name", "Unknown")
    symbol = coin_data.get("symbol", "").upper()

    lines = [f"Token Information: {name} ({symbol})"]
    lines.append("=" * 60)

    # Market data
    lines.append("\n--- Market Data ---")
    current_price = md.get("current_price", {}).get("usd", 0)
    lines.append(f"Current Price (USD): ${current_price:,.2f}")

    market_cap = md.get("market_cap", {}).get("usd", 0)
    lines.append(f"Market Cap (USD): ${market_cap:,.0f}")

    total_volume = md.get("total_volume", {}).get("usd", 0)
    lines.append(f"24h Trading Volume (USD): ${total_volume:,.0f}")

    # Price changes
    lines.append("\n--- Price Changes ---")
    for period in ["1h", "24h", "7d", "30d"]:
        change = md.get(f"price_change_percentage_{period}s")
        if change is not None:
            sign = "+" if change >= 0 else ""
            lines.append(f"{period} Change: {sign}{change:.2f}%")

    # Supply data
    lines.append("\n--- Supply Data ---")
    circulating = md.get("circulating_supply", 0)
    if circulating:
        lines.append(f"Circulating Supply: {circulating:,.0f} {symbol}")

    total_supply = md.get("total_supply")
    if total_supply:
        lines.append(f"Total Supply: {total_supply:,.0f} {symbol}")

    max_supply = md.get("max_supply")
    if max_supply:
        lines.append(f"Max Supply: {max_supply:,.0f} {symbol}")

    # ATH/ATL
    lines.append("\n--- All-Time High/Low ---")
    ath = md.get("ath", {}).get("usd", 0)
    ath_date = md.get("ath_date", {}).get("usd", "")
    if ath:
        lines.append(f"All-Time High: ${ath:,.2f} ({ath_date[:10] if ath_date else 'N/A'})")

    atl = md.get("atl", {}).get("usd", 0)
    atl_date = md.get("atl_date", {}).get("usd", "")
    if atl:
        lines.append(f"All-Time Low: ${atl:,.2f} ({atl_date[:10] if atl_date else 'N/A'})")

    return "\n".join(lines)


async def get_coin_ohlcv(coin_id: str, vs_currency: str = "usd", days: int = 7) -> str:
    """
    Get OHLCV data for a cryptocurrency.

    Args:
        coin_id: CoinGecko coin ID (e.g., 'solana', 'bitcoin', 'ethereum')
        vs_currency: Currency to compare against (default: 'usd')
        days: Number of days of data (default: 7, max: 365)

    Returns:
        Formatted string containing OHLC data for LLM consumption
    """
    async with CoinGeckoProvider() as provider:
        try:
            ohlc_data = await provider.get_ohlc(coin_id, vs_currency, days)
            return _format_ohlc_data(ohlc_data)
        except aiohttp.ClientError as e:
            return f"Error fetching OHLC data: {str(e)}"
        except Exception as e:
            return f"Unexpected error: {str(e)}"


async def get_coin_info(coin_id: str) -> str:
    """
    Get detailed token metadata from CoinGecko.

    Args:
        coin_id: CoinGecko coin ID (e.g., 'solana', 'bitcoin', 'ethereum')

    Returns:
        Formatted string containing token metadata for LLM consumption
    """
    async with CoinGeckoProvider() as provider:
        try:
            coin_data = await provider.get_coin_data(coin_id)
            return _format_coin_info(coin_data)
        except aiohttp.ClientError as e:
            return f"Error fetching coin info: {str(e)}"
        except Exception as e:
            return f"Unexpected error: {str(e)}"


# Module-level provider instance for reuse
_provider: Optional[CoinGeckoProvider] = None


async def _get_provider() -> CoinGeckoProvider:
    """Get or create a module-level provider instance."""
    global _provider
    if _provider is None:
        _provider = CoinGeckoProvider()
    return _provider