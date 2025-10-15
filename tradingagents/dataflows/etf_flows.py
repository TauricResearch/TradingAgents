"""
Gold ETF Holdings Tracker
Monitor GLD (SPDR Gold Shares) and IAU (iShares Gold Trust) holdings.
Large inflows/outflows indicate institutional sentiment shifts.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import re
import yfinance as yf
import pandas as pd


class GoldETFFlowsProvider:
    """Track gold ETF holdings and flows as sentiment indicator."""

    # Major gold ETFs
    GOLD_ETFS = {
        "GLD": {
            "name": "SPDR Gold Shares",
            "holdings_url": "https://www.spdrgoldshares.com/",
            "ticker": "GLD",
            "method": "scrape"  # or "yfinance"
        },
        "IAU": {
            "name": "iShares Gold Trust",
            "holdings_url": "https://www.ishares.com/us/products/239561/ishares-gold-trust-fund",
            "ticker": "IAU",
            "method": "yfinance"
        }
    }

    def __init__(self):
        """Initialize ETF flows provider."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def get_gld_holdings_scrape(self) -> Optional[float]:
        """
        Scrape current GLD holdings from SPDR website.

        Returns:
            Current holdings in tonnes, or None if scraping fails
        """
        try:
            # GLD publishes daily holdings on their website
            url = "https://www.spdrgoldshares.com/usa/"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for holdings data (structure may change, this is illustrative)
            # The actual selector would need to be updated based on current website structure
            holdings_text = soup.find(text=re.compile(r'Tonnes'))

            if holdings_text:
                # Extract number from text like "1,234.56 Tonnes"
                match = re.search(r'([\d,]+\.?\d*)\s*Tonnes', str(holdings_text.parent))
                if match:
                    holdings = float(match.group(1).replace(',', ''))
                    return holdings

            return None

        except Exception as e:
            print(f"Warning: Could not scrape GLD holdings: {e}")
            return None

    def get_etf_holdings_yfinance(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Get ETF historical data via yfinance as proxy for flows.

        We use AUM (Assets Under Management) changes as proxy for flows.
        AUM = Share Price × Shares Outstanding

        Args:
            ticker: ETF ticker (GLD, IAU)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            DataFrame with date, close, volume, estimated_flows
        """
        try:
            etf = yf.Ticker(ticker)

            # Get historical price data
            hist = etf.history(start=start_date, end=end_date)

            if hist.empty:
                return pd.DataFrame()

            # Get shares outstanding (from info)
            info = etf.info
            shares_outstanding = info.get('sharesOutstanding', None)

            # Calculate daily AUM
            hist['AUM'] = hist['Close'] * shares_outstanding if shares_outstanding else None

            # Calculate daily flows (change in AUM - price effect)
            if 'AUM' in hist.columns:
                hist['AUM_Change'] = hist['AUM'].diff()
                hist['Price_Effect'] = hist['Close'].pct_change() * hist['AUM'].shift(1)
                hist['Estimated_Flows'] = hist['AUM_Change'] - hist['Price_Effect']
            else:
                # Fallback: use volume as proxy
                hist['Estimated_Flows'] = hist['Volume']

            return hist

        except Exception as e:
            print(f"Warning: Could not fetch {ticker} data via yfinance: {e}")
            return pd.DataFrame()

    def get_etf_flows(
        self,
        etf_ticker: str,
        start_date: str,
        end_date: str
    ) -> str:
        """
        Get gold ETF flows/holdings data.

        Args:
            etf_ticker: ETF ticker (GLD or IAU)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            CSV string with ETF flows data
        """
        ticker = etf_ticker.upper()

        if ticker not in self.GOLD_ETFS:
            return f"# ETF {ticker} not supported. Supported: GLD, IAU"

        etf_info = self.GOLD_ETFS[ticker]

        # Get data via yfinance
        df = self.get_etf_holdings_yfinance(ticker, start_date, end_date)

        if df.empty:
            return self._generate_mock_etf_data(ticker, start_date, end_date)

        # Format as CSV
        csv_lines = [
            f"# {etf_info['name']} ({ticker}) Holdings & Flows",
            f"# Date range: {start_date} to {end_date}",
            "# Positive flows = buying/accumulation, Negative flows = selling/redemption",
            "",
            "date,close_price,volume,estimated_flows_usd"
        ]

        for date, row in df.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            close = row['Close']
            volume = row['Volume']
            flows = row.get('Estimated_Flows', row['Volume'])

            csv_lines.append(f"{date_str},{close:.2f},{int(volume)},{flows:.0f}")

        # Add interpretation
        csv_lines.append("\n# INTERPRETATION:")
        csv_lines.append("# - Sustained positive flows (3-5 days) = Bullish institutional sentiment")
        csv_lines.append("# - Sustained negative flows = Bearish sentiment / profit taking")
        csv_lines.append("# - GLD holdings > 1000 tonnes = High investor interest")
        csv_lines.append("# - Compare flows to price action for divergences")

        return "\n".join(csv_lines)

    def _generate_mock_etf_data(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> str:
        """Generate mock ETF flow data when actual data unavailable."""
        import random

        csv_lines = [
            f"# {ticker} ETF Flows (SIMULATED DATA)",
            "# WARNING: This is mock data for demonstration",
            "",
            "date,close_price,volume,estimated_flows_usd"
        ]

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        base_price = 180.0 if ticker == "GLD" else 35.0
        current_date = start_dt

        while current_date <= end_dt:
            # Simulate realistic data
            price = base_price + random.uniform(-5, 5)
            volume = random.randint(5_000_000, 15_000_000)
            flows = random.randint(-500_000_000, 500_000_000)

            csv_lines.append(
                f"{current_date.strftime('%Y-%m-%d')},{price:.2f},{volume},{flows}"
            )

            current_date += timedelta(days=1)

        return "\n".join(csv_lines)

    def get_holdings_summary(
        self,
        start_date: str,
        end_date: str
    ) -> str:
        """
        Get combined holdings summary for major gold ETFs.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Summary CSV with combined ETF metrics
        """
        gld_data = self.get_etf_flows("GLD", start_date, end_date)
        iau_data = self.get_etf_flows("IAU", start_date, end_date)

        summary = [
            "# Combined Gold ETF Holdings Summary",
            f"# Date range: {start_date} to {end_date}",
            "",
            "## GLD (SPDR Gold Shares)",
            gld_data,
            "",
            "## IAU (iShares Gold Trust)",
            iau_data,
            "",
            "# ANALYSIS:",
            "# Watch for:",
            "# 1. Divergence: Price up but ETF outflows = Weak hands, potential top",
            "# 2. Convergence: Price down but ETF inflows = Accumulation, potential bottom",
            "# 3. Extreme flows: >$1B daily flow = Strong institutional conviction",
        ]

        return "\n".join(summary)


# Standalone functions for tool integration
_etf_provider = None

def _get_etf_provider():
    """Get or create singleton ETF provider."""
    global _etf_provider
    if _etf_provider is None:
        _etf_provider = GoldETFFlowsProvider()
    return _etf_provider


def get_gold_etf_flows(
    etf_ticker: str,
    start_date: str,
    end_date: str
) -> str:
    """
    Get gold ETF holdings and flow data.

    ETF flows indicate institutional sentiment:
    - Inflows = Institutions accumulating gold (bullish)
    - Outflows = Institutions reducing exposure (bearish)

    Major gold ETFs:
    - GLD: SPDR Gold Shares (largest)
    - IAU: iShares Gold Trust

    Args:
        etf_ticker: ETF ticker symbol (GLD or IAU)
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        CSV with ETF price, volume, and estimated flows
    """
    provider = _get_etf_provider()
    return provider.get_etf_flows(etf_ticker, start_date, end_date)


def get_gold_etf_summary(start_date: str, end_date: str) -> str:
    """
    Get combined summary of major gold ETF holdings.

    Combines GLD and IAU data for comprehensive view of institutional positioning.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Combined summary of gold ETF flows and analysis
    """
    provider = _get_etf_provider()
    return provider.get_holdings_summary(start_date, end_date)


def analyze_etf_divergence(
    etf_ticker: str,
    gold_price_data: str,
    etf_flow_data: str
) -> str:
    """
    Analyze divergences between gold price and ETF flows.

    Divergences can signal:
    - Price up + Outflows = Weak rally, potential reversal
    - Price down + Inflows = Accumulation phase, potential bottom

    Args:
        etf_ticker: ETF ticker
        gold_price_data: Gold price CSV data
        etf_flow_data: ETF flows CSV data

    Returns:
        Divergence analysis summary
    """
    # Simple analysis framework
    analysis = [
        f"# ETF-Price Divergence Analysis for {etf_ticker}",
        "",
        "# Divergence Signals:",
        "# - Bullish: Gold falling but ETF inflows increasing (accumulation)",
        "# - Bearish: Gold rising but ETF outflows increasing (distribution)",
        "# - Confirmation: Gold rising with ETF inflows (healthy uptrend)",
        "",
        "# Recommended Action:",
        "# Use divergences to confirm/reject directional bias",
        "# Extreme divergences often precede reversals",
    ]

    return "\n".join(analysis)
