"""
FRED (Federal Reserve Economic Data) API Integration
Provides macro economic data critical for gold trading analysis.
"""

import os
import requests
from datetime import datetime, timedelta
from typing import Optional
import time


class FREDDataProvider:
    """Federal Reserve Economic Data API provider for macro indicators."""

    BASE_URL = "https://api.stlouisfed.org/fred"

    # FRED Series IDs for key macro indicators
    SERIES_IDS = {
        # US Dollar Index
        "DXY": "DTWEXBGS",  # Trade Weighted U.S. Dollar Index: Broad, Goods and Services
        "DXY_DAILY": "DTWEXBGS",

        # Treasury Yields
        "10Y_YIELD": "DGS10",  # 10-Year Treasury Constant Maturity Rate
        "2Y_YIELD": "DGS2",    # 2-Year Treasury Constant Maturity Rate
        "30Y_YIELD": "DGS30",  # 30-Year Treasury Constant Maturity Rate
        "10Y_TIPS": "DFII10",  # 10-Year Treasury Inflation-Indexed Security

        # Real Yields (calculated as nominal - inflation expectations)
        "10Y_BREAKEVEN": "T10YIE",  # 10-Year Breakeven Inflation Rate

        # Inflation Indicators
        "CPI": "CPIAUCSL",           # Consumer Price Index for All Urban Consumers
        "CORE_CPI": "CPILFESL",      # CPI Less Food and Energy
        "PCE": "PCEPI",              # Personal Consumption Expenditures Price Index
        "CORE_PCE": "PCEPILFE",      # PCE Less Food and Energy (Fed's preferred)
        "PPI": "PPIACO",             # Producer Price Index

        # Federal Reserve Policy
        "FED_FUNDS": "FEDFUNDS",     # Effective Federal Funds Rate
        "FED_BALANCE": "WALCL",      # Fed Balance Sheet (All Assets)

        # Economic Indicators
        "GDP": "GDP",                # Gross Domestic Product
        "UNEMPLOYMENT": "UNRATE",    # Unemployment Rate
        "RETAIL_SALES": "RSXFS",     # Advance Retail Sales

        # Market Indicators
        "VIX": "VIXCLS",             # CBOE Volatility Index (Fear Gauge)
        "SP500": "SP500",            # S&P 500 Index
    }

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize FRED API provider.

        Args:
            api_key: FRED API key. If None, reads from FRED_API_KEY env variable.
        """
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        if not self.api_key:
            raise ValueError(
                "FRED API key required. Set FRED_API_KEY environment variable or pass api_key parameter. "
                "Get free API key at: https://fred.stlouisfed.org/docs/api/api_key.html"
            )

        self.session = requests.Session()
        self.rate_limit_delay = 0.1  # 100ms between requests to respect rate limits

    def _make_request(self, endpoint: str, params: dict) -> dict:
        """Make API request to FRED with error handling."""
        params["api_key"] = self.api_key
        params["file_type"] = "json"

        url = f"{self.BASE_URL}/{endpoint}"

        try:
            time.sleep(self.rate_limit_delay)  # Rate limiting
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 400:
                error_msg = response.json().get("error_message", str(e))
                raise ValueError(f"FRED API error: {error_msg}")
            elif response.status_code == 429:
                raise Exception("FRED API rate limit exceeded. Please wait and try again.")
            else:
                raise Exception(f"FRED API HTTP error: {e}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"FRED API request failed: {e}")

    def get_series(
        self,
        series_id: str,
        start_date: str,
        end_date: str,
        frequency: Optional[str] = None
    ) -> str:
        """
        Get time series data from FRED.

        Args:
            series_id: FRED series ID or friendly name (e.g., "DXY", "10Y_YIELD")
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            frequency: Optional frequency (d=daily, w=weekly, m=monthly, q=quarterly, a=annual)

        Returns:
            CSV-formatted string with date,value columns
        """
        # Resolve friendly name to FRED series ID
        resolved_id = self.SERIES_IDS.get(series_id.upper(), series_id)

        params = {
            "series_id": resolved_id,
            "observation_start": start_date,
            "observation_end": end_date,
        }

        if frequency:
            params["frequency"] = frequency

        data = self._make_request("series/observations", params)

        # Convert to CSV format
        observations = data.get("observations", [])
        if not observations:
            return f"# No data available for {series_id} from {start_date} to {end_date}\n"

        csv_lines = [f"# FRED Series: {resolved_id} ({series_id})"]
        csv_lines.append(f"# Date range: {start_date} to {end_date}")
        csv_lines.append(f"# Total observations: {len(observations)}")
        csv_lines.append("")
        csv_lines.append("date,value")

        for obs in observations:
            if obs["value"] != ".":  # FRED uses "." for missing values
                csv_lines.append(f"{obs['date']},{obs['value']}")

        return "\n".join(csv_lines)

    def get_real_yield(self, start_date: str, end_date: str) -> str:
        """
        Calculate real yield (10Y nominal - 10Y breakeven inflation).

        Real yields are critical for gold: negative real yields = bullish for gold.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            CSV-formatted string with date,real_yield,nominal_yield,breakeven_inflation
        """
        # Get 10Y Treasury yield
        nominal_data = self._make_request("series/observations", {
            "series_id": self.SERIES_IDS["10Y_YIELD"],
            "observation_start": start_date,
            "observation_end": end_date,
        })

        # Get 10Y breakeven inflation
        breakeven_data = self._make_request("series/observations", {
            "series_id": self.SERIES_IDS["10Y_BREAKEVEN"],
            "observation_start": start_date,
            "observation_end": end_date,
        })

        # Create date-indexed dictionaries
        nominal_dict = {obs["date"]: float(obs["value"])
                       for obs in nominal_data.get("observations", [])
                       if obs["value"] != "."}

        breakeven_dict = {obs["date"]: float(obs["value"])
                         for obs in breakeven_data.get("observations", [])
                         if obs["value"] != "."}

        # Calculate real yields
        csv_lines = ["# Real Yield Calculation (10Y Nominal - 10Y Breakeven Inflation)"]
        csv_lines.append(f"# Date range: {start_date} to {end_date}")
        csv_lines.append("")
        csv_lines.append("date,real_yield,nominal_yield,breakeven_inflation")

        # Get common dates
        common_dates = sorted(set(nominal_dict.keys()) & set(breakeven_dict.keys()))

        for date in common_dates:
            nominal = nominal_dict[date]
            breakeven = breakeven_dict[date]
            real_yield = nominal - breakeven
            csv_lines.append(f"{date},{real_yield:.4f},{nominal:.4f},{breakeven:.4f}")

        return "\n".join(csv_lines)

    def get_dxy_analysis(self, start_date: str, end_date: str) -> str:
        """
        Get US Dollar Index with technical context.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            CSV with DXY values and trend analysis
        """
        return self.get_series("DXY", start_date, end_date)

    def get_inflation_summary(self, start_date: str, end_date: str) -> str:
        """
        Get comprehensive inflation data (CPI, Core CPI, PCE, Core PCE).

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            CSV with multiple inflation indicators
        """
        indicators = ["CPI", "CORE_CPI", "PCE", "CORE_PCE"]

        csv_lines = [f"# Inflation Indicators Summary"]
        csv_lines.append(f"# Date range: {start_date} to {end_date}")
        csv_lines.append("")
        csv_lines.append("date,CPI,Core_CPI,PCE,Core_PCE")

        # Fetch all series
        data_dict = {}
        for indicator in indicators:
            data = self._make_request("series/observations", {
                "series_id": self.SERIES_IDS[indicator],
                "observation_start": start_date,
                "observation_end": end_date,
            })

            for obs in data.get("observations", []):
                if obs["value"] != ".":
                    date = obs["date"]
                    if date not in data_dict:
                        data_dict[date] = {}
                    data_dict[date][indicator] = obs["value"]

        # Build CSV
        for date in sorted(data_dict.keys()):
            row = data_dict[date]
            csv_lines.append(
                f"{date},"
                f"{row.get('CPI', '')},"
                f"{row.get('CORE_CPI', '')},"
                f"{row.get('PCE', '')},"
                f"{row.get('CORE_PCE', '')}"
            )

        return "\n".join(csv_lines)

    def get_series_info(self, series_id: str) -> dict:
        """Get metadata about a FRED series."""
        resolved_id = self.SERIES_IDS.get(series_id.upper(), series_id)
        return self._make_request("series", {"series_id": resolved_id})


# Standalone functions for tool integration
_fred_provider = None

def _get_fred_provider():
    """Get or create singleton FRED provider."""
    global _fred_provider
    if _fred_provider is None:
        _fred_provider = FREDDataProvider()
    return _fred_provider


def get_fred_series(
    series: str,
    start_date: str,
    end_date: str,
    frequency: Optional[str] = None
) -> str:
    """
    Get macro economic data from FRED.

    Supported series (use friendly names):
    - DXY: US Dollar Index
    - 10Y_YIELD, 2Y_YIELD, 30Y_YIELD: Treasury yields
    - 10Y_TIPS: Inflation-protected securities
    - 10Y_BREAKEVEN: Inflation expectations
    - CPI, CORE_CPI, PCE, CORE_PCE: Inflation indicators
    - FED_FUNDS: Federal Funds Rate
    - VIX: Volatility index

    Args:
        series: Series ID or friendly name (e.g., "DXY", "10Y_YIELD", "CPI")
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        frequency: Optional frequency (d=daily, w=weekly, m=monthly)

    Returns:
        CSV string with economic data
    """
    provider = _get_fred_provider()
    return provider.get_series(series, start_date, end_date, frequency)


def get_real_yields(start_date: str, end_date: str) -> str:
    """
    Calculate real yields (nominal yield - inflation expectations).

    Real yields are the opportunity cost of holding gold.
    Negative real yields = bullish for gold (no cost to hold non-yielding asset).

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        CSV with real_yield, nominal_yield, breakeven_inflation columns
    """
    provider = _get_fred_provider()
    return provider.get_real_yield(start_date, end_date)


def get_inflation_data(start_date: str, end_date: str) -> str:
    """
    Get comprehensive inflation indicators (CPI, Core CPI, PCE, Core PCE).

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        CSV with multiple inflation metrics
    """
    provider = _get_fred_provider()
    return provider.get_inflation_summary(start_date, end_date)


def get_dxy_data(start_date: str, end_date: str) -> str:
    """
    Get US Dollar Index (DXY) data.

    DXY has strong negative correlation with gold (~-0.7 to -0.9).
    Rising DXY = headwind for gold, Falling DXY = tailwind for gold.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        CSV with DXY values
    """
    provider = _get_fred_provider()
    return provider.get_dxy_analysis(start_date, end_date)
