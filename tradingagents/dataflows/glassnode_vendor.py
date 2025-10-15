"""
Glassnode API Vendor - On-chain cryptocurrency analytics
Provides: Network health, whale activity, mining data, DeFi metrics
"""
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import os


class GlassnodeVendor:
    """Wrapper for Glassnode API to fetch on-chain crypto metrics."""

    BASE_URL = "https://api.glassnode.com/v1/metrics"

    def __init__(self, api_key: str = None):
        """
        Initialize Glassnode API client.

        Args:
            api_key: Glassnode API key (or use GLASSNODE_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("GLASSNODE_API_KEY", "")
        if not self.api_key:
            print("WARNING: No Glassnode API key found. Set GLASSNODE_API_KEY environment variable.")

    def _make_request(
        self,
        endpoint: str,
        asset: str = "BTC",
        since: Optional[str] = None,
        until: Optional[str] = None,
        interval: str = "24h"
    ) -> pd.DataFrame:
        """
        Make API request to Glassnode.

        Args:
            endpoint: Metric endpoint (e.g., 'addresses/active_count')
            asset: Cryptocurrency symbol (BTC, ETH, etc.)
            since: Start date (YYYY-MM-DD or Unix timestamp)
            until: End date (YYYY-MM-DD or Unix timestamp)
            interval: Data interval (1h, 24h, 1w, 1month)

        Returns:
            DataFrame with timestamp and value columns
        """
        url = f"{self.BASE_URL}/{endpoint}"

        params = {
            'a': asset,
            'api_key': self.api_key,
            'i': interval
        }

        if since:
            params['s'] = since
        if until:
            params['u'] = until

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            # Convert to DataFrame
            df = pd.DataFrame(data)
            if 't' in df.columns and 'v' in df.columns:
                df['timestamp'] = pd.to_datetime(df['t'], unit='s')
                df['value'] = df['v']
                df = df[['timestamp', 'value']].set_index('timestamp')

            return df

        except requests.exceptions.RequestException as e:
            print(f"Glassnode API error for {endpoint}: {e}")
            return pd.DataFrame()

    # Network Health Metrics

    def get_active_addresses(self, asset: str = "BTC", days: int = 30) -> pd.DataFrame:
        """Get number of unique active addresses."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._make_request('addresses/active_count', asset=asset, since=since)

    def get_new_addresses(self, asset: str = "BTC", days: int = 30) -> pd.DataFrame:
        """Get number of new addresses created."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._make_request('addresses/new_non_zero_count', asset=asset, since=since)

    def get_transaction_count(self, asset: str = "BTC", days: int = 30) -> pd.DataFrame:
        """Get number of transactions per day."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._make_request('transactions/count', asset=asset, since=since)

    def get_hash_rate(self, asset: str = "BTC", days: int = 30) -> pd.DataFrame:
        """Get network hash rate (PoW chains only)."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._make_request('mining/hash_rate_mean', asset=asset, since=since)

    # Whale and Exchange Metrics

    def get_exchange_balance(self, asset: str = "BTC", days: int = 30) -> pd.DataFrame:
        """Get total balance on exchanges."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._make_request('distribution/balance_exchanges', asset=asset, since=since)

    def get_exchange_inflow(self, asset: str = "BTC", days: int = 30) -> pd.DataFrame:
        """Get inflow to exchanges (potential selling pressure)."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._make_request('transactions/transfers_volume_exchanges_in', asset=asset, since=since)

    def get_exchange_outflow(self, asset: str = "BTC", days: int = 30) -> pd.DataFrame:
        """Get outflow from exchanges (potential accumulation)."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._make_request('transactions/transfers_volume_exchanges_out', asset=asset, since=since)

    def get_whale_balance(self, asset: str = "BTC", days: int = 30) -> pd.DataFrame:
        """Get balance held by whales (>1000 BTC or equivalent)."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._make_request('distribution/balance_1pct_holders', asset=asset, since=since)

    # Valuation Metrics

    def get_nvt_ratio(self, asset: str = "BTC", days: int = 30) -> pd.DataFrame:
        """Get NVT (Network Value to Transactions) ratio."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._make_request('indicators/nvt', asset=asset, since=since)

    def get_mvrv_ratio(self, asset: str = "BTC", days: int = 30) -> pd.DataFrame:
        """Get MVRV (Market Value to Realized Value) ratio."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._make_request('indicators/mvrv', asset=asset, since=since)

    def get_realized_price(self, asset: str = "BTC", days: int = 30) -> pd.DataFrame:
        """Get realized price (average price at which coins last moved)."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._make_request('indicators/realized_price_usd', asset=asset, since=since)

    # Supply Metrics

    def get_supply_in_profit(self, asset: str = "BTC", days: int = 30) -> pd.DataFrame:
        """Get percentage of supply in profit."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._make_request('indicators/supply_profit_relative', asset=asset, since=since)

    def get_hodl_waves(self, asset: str = "BTC", days: int = 30) -> pd.DataFrame:
        """Get HODL waves (age distribution of coins)."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        return self._make_request('supply/hodl_waves', asset=asset, since=since)


# Convenience functions for integration with existing dataflow interface

def get_onchain_metrics(asset: str = "BTC", days: int = 30) -> str:
    """
    Get comprehensive on-chain metrics summary.

    Args:
        asset: Cryptocurrency symbol (BTC, ETH, etc.)
        days: Number of days of historical data

    Returns:
        Formatted string with on-chain metrics
    """
    vendor = GlassnodeVendor()

    result = f"On-Chain Metrics for {asset} (Last {days} days):\n\n"

    try:
        # Network Health
        active_addr = vendor.get_active_addresses(asset, days)
        if not active_addr.empty:
            latest = active_addr['value'].iloc[-1]
            change = ((active_addr['value'].iloc[-1] / active_addr['value'].iloc[0]) - 1) * 100
            result += f"Active Addresses: {latest:,.0f} ({change:+.1f}%)\n"

        txn_count = vendor.get_transaction_count(asset, days)
        if not txn_count.empty:
            latest = txn_count['value'].iloc[-1]
            change = ((txn_count['value'].iloc[-1] / txn_count['value'].iloc[0]) - 1) * 100
            result += f"Daily Transactions: {latest:,.0f} ({change:+.1f}%)\n"

        # Exchange Flows
        exchange_balance = vendor.get_exchange_balance(asset, days)
        if not exchange_balance.empty:
            latest = exchange_balance['value'].iloc[-1]
            change = ((exchange_balance['value'].iloc[-1] / exchange_balance['value'].iloc[0]) - 1) * 100
            result += f"\nExchange Balance: {latest:,.0f} {asset} ({change:+.1f}%)\n"

        inflow = vendor.get_exchange_inflow(asset, days)
        outflow = vendor.get_exchange_outflow(asset, days)
        if not inflow.empty and not outflow.empty:
            net_flow = outflow['value'].iloc[-1] - inflow['value'].iloc[-1]
            flow_direction = "OUTFLOW (Bullish)" if net_flow > 0 else "INFLOW (Bearish)"
            result += f"Net Exchange Flow: {abs(net_flow):,.0f} {asset} {flow_direction}\n"

        # Valuation Metrics
        mvrv = vendor.get_mvrv_ratio(asset, days)
        if not mvrv.empty:
            latest = mvrv['value'].iloc[-1]
            interpretation = "Overvalued" if latest > 3 else "Undervalued" if latest < 1 else "Fair Value"
            result += f"\nMVRV Ratio: {latest:.2f} ({interpretation})\n"

        nvt = vendor.get_nvt_ratio(asset, days)
        if not nvt.empty:
            latest = nvt['value'].iloc[-1]
            result += f"NVT Ratio: {latest:.2f}\n"

        # Profitability
        supply_profit = vendor.get_supply_in_profit(asset, days)
        if not supply_profit.empty:
            latest = supply_profit['value'].iloc[-1] * 100
            sentiment = "Bullish" if latest > 75 else "Bearish" if latest < 50 else "Neutral"
            result += f"\nSupply in Profit: {latest:.1f}% ({sentiment})\n"

        result += "\n[Note: On-chain data requires Glassnode API key]"

    except Exception as e:
        result += f"\nError fetching on-chain data: {e}\n"
        result += "Ensure GLASSNODE_API_KEY is set in environment variables."

    return result


def get_exchange_flow_analysis(asset: str = "BTC", days: int = 7) -> str:
    """
    Analyze exchange inflows/outflows (whale movement indicator).

    Args:
        asset: Cryptocurrency symbol
        days: Number of days to analyze

    Returns:
        Formatted string with flow analysis
    """
    vendor = GlassnodeVendor()

    result = f"Exchange Flow Analysis for {asset} (Last {days} days):\n\n"

    try:
        inflow = vendor.get_exchange_inflow(asset, days)
        outflow = vendor.get_exchange_outflow(asset, days)

        if not inflow.empty and not outflow.empty:
            # Calculate net flows
            df = pd.DataFrame({
                'inflow': inflow['value'],
                'outflow': outflow['value']
            })
            df['net_flow'] = df['outflow'] - df['inflow']

            total_inflow = df['inflow'].sum()
            total_outflow = df['outflow'].sum()
            net_flow = total_outflow - total_inflow

            result += f"Total Inflow: {total_inflow:,.0f} {asset}\n"
            result += f"Total Outflow: {total_outflow:,.0f} {asset}\n"
            result += f"Net Flow: {net_flow:,.0f} {asset}\n\n"

            if net_flow > 0:
                result += "⬆️ NET OUTFLOW - Bullish Signal (Accumulation)\n"
                result += "Coins moving off exchanges suggests holders are accumulating for long-term.\n"
            else:
                result += "⬇️ NET INFLOW - Bearish Signal (Distribution)\n"
                result += "Coins moving to exchanges suggests potential selling pressure.\n"

            # Calculate flow ratio
            flow_ratio = total_outflow / total_inflow if total_inflow > 0 else 0
            result += f"\nOutflow/Inflow Ratio: {flow_ratio:.2f}\n"

    except Exception as e:
        result += f"Error: {e}\n"

    return result


def get_whale_activity(asset: str = "BTC", days: int = 30) -> str:
    """
    Analyze whale wallet activity.

    Args:
        asset: Cryptocurrency symbol
        days: Number of days to analyze

    Returns:
        Formatted string with whale analysis
    """
    vendor = GlassnodeVendor()

    result = f"Whale Activity Analysis for {asset} (Last {days} days):\n\n"

    try:
        whale_balance = vendor.get_whale_balance(asset, days)

        if not whale_balance.empty:
            current = whale_balance['value'].iloc[-1]
            previous = whale_balance['value'].iloc[0]
            change = current - previous
            change_pct = (change / previous) * 100

            result += f"Top 1% Holders Balance: {current:,.0f} {asset}\n"
            result += f"Change: {change:+,.0f} {asset} ({change_pct:+.2f}%)\n\n"

            if change_pct > 1:
                result += "🐋 WHALE ACCUMULATION - Bullish Signal\n"
                result += "Large holders are increasing positions.\n"
            elif change_pct < -1:
                result += "🐋 WHALE DISTRIBUTION - Bearish Signal\n"
                result += "Large holders are reducing positions.\n"
            else:
                result += "🐋 WHALE NEUTRAL - No significant change\n"

    except Exception as e:
        result += f"Error: {e}\n"

    return result
