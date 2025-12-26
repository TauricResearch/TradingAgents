"""
FRED API Data Retrieval Functions.

This module provides high-level functions for retrieving economic data from FRED:
- Interest rates (Federal Funds Rate)
- Treasury rates (2Y, 5Y, 10Y, 30Y yields)
- Money supply (M1, M2)
- GDP (nominal and real)
- Inflation (CPI, PCE)
- Unemployment rate
- Generic series retrieval

All functions return pandas DataFrames on success or error strings on failure.
Functions automatically handle caching, retry logic, and error recovery.

Usage:
    from spektiv.dataflows.fred import get_interest_rates, get_treasury_rates

    # Get federal funds rate
    data = get_interest_rates()

    # Get 10-year treasury yield with date range
    data = get_treasury_rates(maturity='10Y', start_date='2024-01-01', end_date='2024-12-31')

Requirements:
    - fredapi package: pip install fredapi
    - FRED_API_KEY environment variable must be set
"""

import pandas as pd
from typing import Union, Optional
from .fred_common import (
    _make_fred_request,
    FredRateLimitError,
    FredInvalidSeriesError,
)


# ============================================================================
# FRED Series ID Mappings
# ============================================================================

FRED_SERIES = {
    # Interest Rates
    'FEDFUNDS': 'FEDFUNDS',  # Federal Funds Effective Rate
    'EFFR': 'FEDFUNDS',      # Alias for Federal Funds Rate

    # Treasury Rates
    'DGS2': 'DGS2',          # 2-Year Treasury Constant Maturity Rate
    'DGS5': 'DGS5',          # 5-Year Treasury Constant Maturity Rate
    'DGS10': 'DGS10',        # 10-Year Treasury Constant Maturity Rate
    'DGS30': 'DGS30',        # 30-Year Treasury Constant Maturity Rate

    # Money Supply
    'M1SL': 'M1SL',          # M1 Money Stock
    'M2SL': 'M2SL',          # M2 Money Stock

    # GDP
    'GDP': 'GDP',            # Gross Domestic Product (nominal)
    'GDPC1': 'GDPC1',        # Real Gross Domestic Product

    # Inflation
    'CPIAUCSL': 'CPIAUCSL',  # Consumer Price Index for All Urban Consumers
    'PCEPI': 'PCEPI',        # Personal Consumption Expenditures Price Index

    # Unemployment
    'UNRATE': 'UNRATE',      # Unemployment Rate
}

# Treasury maturity mappings
TREASURY_MATURITIES = {
    '2Y': 'DGS2',
    '5Y': 'DGS5',
    '10Y': 'DGS10',
    '30Y': 'DGS30',
}

# Money supply measure mappings
MONEY_SUPPLY_MEASURES = {
    'M1': 'M1SL',
    'M2': 'M2SL',
}

# GDP frequency mappings
GDP_FREQUENCIES = {
    'quarterly': 'GDP',
    'real': 'GDPC1',
    'nominal': 'GDP',
    'annual': 'GDPA',
}

# Inflation measure mappings
INFLATION_MEASURES = {
    'CPI': 'CPIAUCSL',
    'CORE': 'CPILFESL',
    'PCE': 'PCEPI',
}


# ============================================================================
# Data Retrieval Functions
# ============================================================================

def get_interest_rates(
    series_id: str = 'FEDFUNDS',
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    use_cache: bool = True
) -> Union[pd.DataFrame, str]:
    """
    Retrieve interest rate data from FRED.

    Args:
        series_id: FRED series ID (default: 'FEDFUNDS' for Federal Funds Rate)
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)
        use_cache: Whether to use caching (default: True)

    Returns:
        pd.DataFrame with 'date' and 'value' columns on success
        str with error message on failure

    Examples:
        >>> data = get_interest_rates()  # Get federal funds rate
        >>> data = get_interest_rates(start_date='2024-01-01', end_date='2024-12-31')
    """
    try:
        # Make API request
        data = _make_fred_request(series_id, start_date=start_date, end_date=end_date)

        return data

    except FredRateLimitError as e:
        return f"Error: FRED API rate limit exceeded. Please try again later. Details: {e}"
    except FredInvalidSeriesError as e:
        return f"Error: Invalid FRED series ID '{series_id}'. Details: {e}"
    except ValueError as e:
        return f"Error: Invalid input parameters. Details: {e}"
    except Exception as e:
        return f"Error retrieving interest rate data: {e}"


def get_treasury_rates(
    maturity: str = '10Y',
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    use_cache: bool = True
) -> Union[pd.DataFrame, str]:
    """
    Retrieve Treasury yield data from FRED.

    Args:
        maturity: Treasury maturity ('2Y', '5Y', '10Y', or '30Y', default: '10Y')
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)

    Returns:
        pd.DataFrame with 'date' and 'value' columns on success
        str with error message on failure

    Examples:
        >>> data = get_treasury_rates()  # Get 10-year yield
        >>> data = get_treasury_rates(maturity='2Y', start_date='2024-01-01')
    """
    try:
        # Map maturity to series ID
        series_id = TREASURY_MATURITIES.get(maturity)
        if not series_id:
            return f"Error: Invalid maturity '{maturity}'. Valid options: {list(TREASURY_MATURITIES.keys())}"

        # Make API request (caching handled internally)
        data = _make_fred_request(series_id, start_date=start_date, end_date=end_date)

        return data

    except FredRateLimitError as e:
        return f"Error: FRED API rate limit exceeded. Please try again later. Details: {e}"
    except FredInvalidSeriesError as e:
        return f"Error: Invalid FRED series. Details: {e}"
    except ValueError as e:
        return f"Error: Invalid input parameters. Details: {e}"
    except Exception as e:
        return f"Error retrieving treasury rate data: {e}"


def get_money_supply(
    measure: str = 'M2',
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    use_cache: bool = True
) -> Union[pd.DataFrame, str]:
    """
    Retrieve money supply data from FRED.

    Args:
        measure: Money supply measure ('M1' or 'M2', default: 'M2')
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)

    Returns:
        pd.DataFrame with 'date' and 'value' columns (values in billions) on success
        str with error message on failure

    Examples:
        >>> data = get_money_supply()  # Get M2 money supply
        >>> data = get_money_supply(measure='M1', start_date='2024-01-01')
    """
    try:
        # Map measure to series ID
        series_id = MONEY_SUPPLY_MEASURES.get(measure)
        if not series_id:
            return f"Error: Invalid measure '{measure}'. Valid options: {list(MONEY_SUPPLY_MEASURES.keys())}"

        # Make API request (caching handled internally)
        data = _make_fred_request(series_id, start_date=start_date, end_date=end_date)

        return data

    except FredRateLimitError as e:
        return f"Error: FRED API rate limit exceeded. Please try again later. Details: {e}"
    except FredInvalidSeriesError as e:
        return f"Error: Invalid FRED series. Details: {e}"
    except ValueError as e:
        return f"Error: Invalid input parameters. Details: {e}"
    except Exception as e:
        return f"Error retrieving money supply data: {e}"


def get_gdp(
    frequency: str = 'quarterly',
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    use_cache: bool = True
) -> Union[pd.DataFrame, str]:
    """
    Retrieve GDP data from FRED.

    Args:
        frequency: GDP type ('quarterly', 'nominal', 'real', or 'annual', default: 'quarterly')
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)

    Returns:
        pd.DataFrame with 'date' and 'value' columns (values in billions) on success
        str with error message on failure

    Examples:
        >>> data = get_gdp()  # Get quarterly nominal GDP
        >>> data = get_gdp(frequency='real', start_date='2024-01-01')
    """
    try:
        # Map frequency to series ID
        series_id = GDP_FREQUENCIES.get(frequency)
        if not series_id:
            return f"Error: Invalid frequency '{frequency}'. Valid options: {list(GDP_FREQUENCIES.keys())}"

        # Make API request (caching handled internally)
        data = _make_fred_request(series_id, start_date=start_date, end_date=end_date)

        return data

    except FredRateLimitError as e:
        return f"Error: FRED API rate limit exceeded. Please try again later. Details: {e}"
    except FredInvalidSeriesError as e:
        return f"Error: Invalid FRED series. Details: {e}"
    except ValueError as e:
        return f"Error: Invalid input parameters. Details: {e}"
    except Exception as e:
        return f"Error retrieving GDP data: {e}"


def get_inflation(
    measure: str = 'CPI',
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    use_cache: bool = True
) -> Union[pd.DataFrame, str]:
    """
    Retrieve inflation data from FRED.

    Args:
        measure: Inflation measure ('CPI', 'CORE', or 'PCE', default: 'CPI')
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)

    Returns:
        pd.DataFrame with 'date' and 'value' columns (index values) on success
        str with error message on failure

    Examples:
        >>> data = get_inflation()  # Get CPI data
        >>> data = get_inflation(measure='PCE', start_date='2024-01-01')
    """
    try:
        # Map measure to series ID
        series_id = INFLATION_MEASURES.get(measure)
        if not series_id:
            return f"Error: Invalid measure '{measure}'. Valid options: {list(INFLATION_MEASURES.keys())}"

        # Make API request (caching handled internally)
        data = _make_fred_request(series_id, start_date=start_date, end_date=end_date)

        return data

    except FredRateLimitError as e:
        return f"Error: FRED API rate limit exceeded. Please try again later. Details: {e}"
    except FredInvalidSeriesError as e:
        return f"Error: Invalid FRED series. Details: {e}"
    except ValueError as e:
        return f"Error: Invalid input parameters. Details: {e}"
    except Exception as e:
        return f"Error retrieving inflation data: {e}"


def get_unemployment(
    series_id: str = 'UNRATE',
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    use_cache: bool = True
) -> Union[pd.DataFrame, str]:
    """
    Retrieve unemployment rate data from FRED.

    Args:
        series_id: FRED series ID (default: 'UNRATE' for U.S. unemployment rate)
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)

    Returns:
        pd.DataFrame with 'date' and 'value' columns (percentage) on success
        str with error message on failure

    Examples:
        >>> data = get_unemployment()  # Get U.S. unemployment rate
        >>> data = get_unemployment(start_date='2024-01-01', end_date='2024-12-31')
    """
    try:
        # Make API request
        data = _make_fred_request(series_id, start_date=start_date, end_date=end_date)

        return data

    except FredRateLimitError as e:
        return f"Error: FRED API rate limit exceeded. Please try again later. Details: {e}"
    except FredInvalidSeriesError as e:
        return f"Error: Invalid FRED series ID '{series_id}'. Details: {e}"
    except ValueError as e:
        return f"Error: Invalid input parameters. Details: {e}"
    except Exception as e:
        return f"Error retrieving unemployment data: {e}"


def get_fred_series(
    series_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    use_cache: bool = True
) -> Union[pd.DataFrame, str]:
    """
    Retrieve any FRED series data by series ID.

    This is a generic function that can retrieve any FRED series.
    Use specific functions (get_interest_rates, get_treasury_rates, etc.)
    for better validation and error messages.

    Args:
        series_id: FRED series ID (e.g., 'FEDFUNDS', 'DGS10', 'UNRATE')
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)

    Returns:
        pd.DataFrame with 'date' and 'value' columns on success
        str with error message on failure

    Examples:
        >>> data = get_fred_series('FEDFUNDS')  # Get federal funds rate
        >>> data = get_fred_series('DGS10', start_date='2024-01-01')
    """
    try:
        # Validate series_id
        if not series_id or not isinstance(series_id, str):
            return "Error: series_id must be a non-empty string"

        # Make API request (caching handled internally)
        data = _make_fred_request(series_id, start_date=start_date, end_date=end_date)

        return data

    except FredRateLimitError as e:
        return f"Error: FRED API rate limit exceeded. Please try again later. Details: {e}"
    except FredInvalidSeriesError as e:
        return f"Error: Invalid FRED series ID '{series_id}'. Details: {e}"
    except ValueError as e:
        return f"Error: Invalid input parameters. Details: {e}"
    except Exception as e:
        return f"Error retrieving FRED series data: {e}"
