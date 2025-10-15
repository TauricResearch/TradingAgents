"""
Messari API Vendor - Crypto fundamental data and research
Provides: Asset profiles, metrics, tokenomics, project info
"""
import requests
import pandas as pd
from typing import Optional, Dict, List, Any
import os


class MessariVendor:
    """Wrapper for Messari API to fetch crypto fundamental data."""

    BASE_URL = "https://data.messari.io/api"

    def __init__(self, api_key: str = None):
        """
        Initialize Messari API client.

        Args:
            api_key: Messari API key (optional for basic endpoints)
        """
        self.api_key = api_key or os.getenv("MESSARI_API_KEY", "")
        self.headers = {}
        if self.api_key:
            self.headers['x-messari-api-key'] = self.api_key

    def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """
        Make API request to Messari.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response data
        """
        url = f"{self.BASE_URL}/{endpoint}"

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"Messari API error for {endpoint}: {e}")
            return {}

    def get_asset_profile(self, asset_key: str) -> Dict[str, Any]:
        """
        Get comprehensive asset profile.

        Args:
            asset_key: Asset slug (e.g., 'bitcoin', 'ethereum')

        Returns:
            Dictionary with asset profile data
        """
        endpoint = f"v2/assets/{asset_key}/profile"
        data = self._make_request(endpoint)
        return data.get('data', {})

    def get_asset_metrics(self, asset_key: str) -> Dict[str, Any]:
        """
        Get current asset metrics (price, market cap, volume, etc.).

        Args:
            asset_key: Asset slug

        Returns:
            Dictionary with current metrics
        """
        endpoint = f"v1/assets/{asset_key}/metrics"
        data = self._make_request(endpoint)
        return data.get('data', {})

    def get_market_data(self, asset_key: str) -> Dict[str, Any]:
        """
        Get detailed market data.

        Args:
            asset_key: Asset slug

        Returns:
            Dictionary with market data
        """
        endpoint = f"v1/assets/{asset_key}/metrics/market-data"
        data = self._make_request(endpoint)
        return data.get('data', {})

    def get_all_assets(self, limit: int = 100) -> List[Dict]:
        """
        Get list of all assets.

        Args:
            limit: Number of assets to return

        Returns:
            List of asset dictionaries
        """
        endpoint = "v2/assets"
        params = {'limit': limit}
        data = self._make_request(endpoint, params)
        return data.get('data', [])

    def get_news(self, asset_key: str = None, limit: int = 20) -> List[Dict]:
        """
        Get crypto news.

        Args:
            asset_key: Asset slug (optional, for asset-specific news)
            limit: Number of news items

        Returns:
            List of news items
        """
        if asset_key:
            endpoint = f"v1/assets/{asset_key}/news"
        else:
            endpoint = "v1/news"

        params = {'limit': limit}
        data = self._make_request(endpoint, params)
        return data.get('data', [])

    def get_timeseries(
        self,
        asset_key: str,
        metric_id: str,
        start: str = None,
        end: str = None,
        interval: str = '1d'
    ) -> pd.DataFrame:
        """
        Get historical timeseries data for a metric.

        Args:
            asset_key: Asset slug
            metric_id: Metric ID (e.g., 'price', 'volume', 'active_addresses')
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)
            interval: Data interval (1d, 1w, 1m)

        Returns:
            DataFrame with timeseries data
        """
        endpoint = f"v1/assets/{asset_key}/metrics/{metric_id}/time-series"
        params = {
            'interval': interval
        }
        if start:
            params['start'] = start
        if end:
            params['end'] = end

        data = self._make_request(endpoint, params)
        values = data.get('data', {}).get('values', [])

        if values:
            df = pd.DataFrame(values, columns=['timestamp', 'value'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df
        else:
            return pd.DataFrame()


# Convenience functions for integration with existing dataflow interface

def get_crypto_fundamentals_messari(asset_key: str) -> str:
    """
    Get crypto fundamental data from Messari.

    Args:
        asset_key: Asset slug (e.g., 'bitcoin', 'ethereum', 'solana')

    Returns:
        Formatted string with fundamental data
    """
    vendor = MessariVendor()

    result = f"Fundamental Analysis for {asset_key.upper()} (Messari Data):\n\n"

    try:
        # Get asset profile
        profile = vendor.get_asset_profile(asset_key)

        if profile:
            general = profile.get('profile', {}).get('general', {})
            economics = profile.get('profile', {}).get('economics', {})
            technology = profile.get('profile', {}).get('technology', {})

            # General Info
            result += "=== PROJECT OVERVIEW ===\n"
            result += f"Name: {general.get('overview', {}).get('project_name', 'N/A')}\n"
            result += f"Tagline: {general.get('overview', {}).get('tagline', 'N/A')}\n"
            result += f"Category: {general.get('overview', {}).get('category', 'N/A')}\n"
            result += f"Sector: {general.get('overview', {}).get('sector', 'N/A')}\n\n"

            # Tokenomics
            result += "=== TOKENOMICS ===\n"
            token_type = economics.get('token', {}).get('token_type', 'N/A')
            token_usage = economics.get('token', {}).get('token_usage', 'N/A')
            result += f"Token Type: {token_type}\n"
            result += f"Token Usage: {token_usage}\n"

            # Launch info
            launch = economics.get('launch', {})
            if launch:
                result += f"Launch Date: {launch.get('general', {}).get('launch_date', 'N/A')}\n"
                result += f"Launch Style: {launch.get('general', {}).get('launch_style', 'N/A')}\n"

            # Consensus
            result += f"\n=== TECHNOLOGY ===\n"
            result += f"Consensus: {technology.get('overview', {}).get('consensus_mechanism', 'N/A')}\n"
            result += f"Hashing Algorithm: {technology.get('overview', {}).get('hashing_algorithm', 'N/A')}\n"

        # Get current metrics
        metrics = vendor.get_asset_metrics(asset_key)

        if metrics:
            market_data = metrics.get('market_data', {})
            marketcap = metrics.get('marketcap', {})
            supply = metrics.get('supply', {})

            result += f"\n=== MARKET METRICS ===\n"
            result += f"Price (USD): ${market_data.get('price_usd', 0):,.2f}\n"
            result += f"Market Cap: ${marketcap.get('current_marketcap_usd', 0):,.0f}\n"
            result += f"24h Volume: ${market_data.get('real_volume_last_24_hours', 0):,.0f}\n"
            result += f"24h Change: {market_data.get('percent_change_usd_last_24_hours', 0):.2f}%\n"

            result += f"\n=== SUPPLY METRICS ===\n"
            result += f"Circulating Supply: {supply.get('circulating', 0):,.0f}\n"
            result += f"Total Supply: {supply.get('y_2050', 0):,.0f}\n"
            result += f"Max Supply: {supply.get('max', 'Unlimited') if supply.get('max') else 'Unlimited'}\n"

            # Calculate inflation rate
            circulating = supply.get('circulating', 0)
            y_plus_10 = supply.get('y_plus_ten', 0)
            if circulating > 0 and y_plus_10 > circulating:
                annual_inflation = ((y_plus_10 / circulating) ** 0.1 - 1) * 100
                result += f"Est. Annual Inflation: {annual_inflation:.2f}%\n"

            # ROI metrics
            roi_data = metrics.get('roi_data', {})
            if roi_data:
                result += f"\n=== ROI METRICS ===\n"
                result += f"ATH Price: ${roi_data.get('price_at_ath', 0):,.2f}\n"
                result += f"% Down from ATH: {roi_data.get('percent_down_from_ath', 0):.1f}%\n"

    except Exception as e:
        result += f"\nError fetching Messari data: {e}\n"
        result += "Note: Some data may require Messari API key."

    return result


def get_crypto_news_messari(asset_key: str = None, limit: int = 10) -> str:
    """
    Get crypto news from Messari.

    Args:
        asset_key: Asset slug (optional, for asset-specific news)
        limit: Number of news items

    Returns:
        Formatted string with news
    """
    vendor = MessariVendor()

    if asset_key:
        result = f"Latest News for {asset_key.upper()} (Messari):\n\n"
    else:
        result = f"Latest Crypto News (Messari):\n\n"

    try:
        news_items = vendor.get_news(asset_key, limit)

        for i, item in enumerate(news_items[:limit], 1):
            title = item.get('title', 'No title')
            published = item.get('published_at', 'Unknown date')
            url = item.get('url', '')

            result += f"{i}. {title}\n"
            result += f"   Published: {published}\n"
            result += f"   URL: {url}\n\n"

    except Exception as e:
        result += f"Error fetching news: {e}\n"

    return result


def get_crypto_market_overview(limit: int = 20) -> str:
    """
    Get overview of top crypto assets.

    Args:
        limit: Number of assets to include

    Returns:
        Formatted string with market overview
    """
    vendor = MessariVendor()

    result = f"Crypto Market Overview - Top {limit} Assets (Messari):\n\n"

    try:
        assets = vendor.get_all_assets(limit)

        result += f"{'Rank':<6}{'Symbol':<8}{'Price':<15}{'Market Cap':<20}{'24h %':<10}\n"
        result += "=" * 70 + "\n"

        for asset in assets:
            rank = asset.get('metrics', {}).get('marketcap', {}).get('rank', 0)
            symbol = asset.get('symbol', 'N/A')
            price = asset.get('metrics', {}).get('market_data', {}).get('price_usd', 0)
            mcap = asset.get('metrics', {}).get('marketcap', {}).get('current_marketcap_usd', 0)
            change_24h = asset.get('metrics', {}).get('market_data', {}).get('percent_change_usd_last_24_hours', 0)

            result += f"{rank:<6}{symbol:<8}${price:<14,.2f}${mcap:<19,.0f}{change_24h:>6.2f}%\n"

    except Exception as e:
        result += f"Error: {e}\n"

    return result


def get_tokenomics_analysis(asset_key: str) -> str:
    """
    Detailed tokenomics analysis.

    Args:
        asset_key: Asset slug

    Returns:
        Formatted string with tokenomics analysis
    """
    vendor = MessariVendor()

    result = f"Tokenomics Analysis for {asset_key.upper()}:\n\n"

    try:
        profile = vendor.get_asset_profile(asset_key)
        metrics = vendor.get_asset_metrics(asset_key)

        if profile and metrics:
            economics = profile.get('profile', {}).get('economics', {})
            supply = metrics.get('supply', {})
            marketcap = metrics.get('marketcap', {})

            # Supply Distribution
            result += "=== SUPPLY SCHEDULE ===\n"
            result += f"Circulating: {supply.get('circulating', 0):,.0f}\n"
            result += f"Total Mined/Staked: {supply.get('y_2050', 0):,.0f}\n"
            result += f"Maximum Supply: {supply.get('max', 'Unlimited') if supply.get('max') else 'Unlimited'}\n"

            circ = supply.get('circulating', 0)
            total = supply.get('y_2050', 0)
            if total > 0:
                circ_pct = (circ / total) * 100
                result += f"% of Total Circulating: {circ_pct:.1f}%\n"

            # Issuance
            token_details = economics.get('token', {})
            result += f"\n=== TOKEN DETAILS ===\n"
            result += f"Type: {token_details.get('token_type', 'N/A')}\n"
            result += f"Usage: {token_details.get('token_usage', 'N/A')}\n"
            result += f"Sale Details: {token_details.get('token_sale_details', 'N/A')}\n"

            # Market Cap Analysis
            result += f"\n=== VALUATION ===\n"
            result += f"Market Cap: ${marketcap.get('current_marketcap_usd', 0):,.0f}\n"
            result += f"Rank: #{marketcap.get('rank', 'N/A')}\n"

            # Calculate dilution
            if circ > 0 and total > circ:
                dilution = ((total - circ) / circ) * 100
                result += f"Potential Dilution: {dilution:.1f}%\n"
                result += f"Fully Diluted Market Cap: ${marketcap.get('current_marketcap_usd', 0) * (total / circ):,.0f}\n"

    except Exception as e:
        result += f"Error: {e}\n"

    return result
