"""
FRED API Core Utilities.

This module provides core utilities for accessing the Federal Reserve Economic Data (FRED) API:
- API key management
- Custom exceptions for rate limiting and invalid series
- Date formatting for FRED API
- Request wrapper with retry logic and exponential backoff
- Cache management for reducing API calls

Usage:
    from spektiv.dataflows.fred_common import get_api_key, _make_fred_request

    api_key = get_api_key()
    data = _make_fred_request('FEDFUNDS', start_date='2024-01-01', end_date='2024-12-31')

Requirements:
    - fredapi package: pip install fredapi
    - FRED_API_KEY environment variable must be set
"""

import os
import time
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Union

# Try to import fredapi, but allow it to be mocked in tests
try:
    from fredapi import Fred
except ImportError:
    Fred = None


# ============================================================================
# Configuration
# ============================================================================

# Cache directory for FRED data
CACHE_DIR = Path.home() / ".cache" / "fred"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Cache TTL in hours
CACHE_TTL_HOURS = 24


# ============================================================================
# Custom Exceptions
# ============================================================================

class FredRateLimitError(Exception):
    """Exception raised when FRED API rate limit is exceeded."""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class FredInvalidSeriesError(Exception):
    """Exception raised when FRED series ID is invalid or not found."""
    def __init__(self, message: str, series_id: Optional[str] = None):
        super().__init__(message)
        self.series_id = series_id


# ============================================================================
# API Key Management
# ============================================================================

def get_api_key() -> str:
    """
    Retrieve the FRED API key from environment variables.

    Returns:
        str: The FRED API key

    Raises:
        ValueError: If FRED_API_KEY environment variable is not set or empty
    """
    api_key = os.getenv("FRED_API_KEY")
    if not api_key or not api_key.strip():
        raise ValueError("FRED_API_KEY environment variable is not set")
    return api_key


# ============================================================================
# Date Formatting
# ============================================================================

def format_date_for_fred(date_input: Union[str, datetime, 'date', int, None]) -> Optional[str]:
    """
    Convert various date formats to YYYY-MM-DD format required by FRED API.

    Args:
        date_input: Date as string, datetime/date object, timestamp (int), or None

    Returns:
        Date string in YYYY-MM-DD format, or None if input is None

    Raises:
        ValueError: If date format is invalid or unsupported
    """
    if date_input is None:
        return None

    # Handle datetime.date objects (not datetime)
    if hasattr(date_input, 'year') and hasattr(date_input, 'month') and hasattr(date_input, 'day'):
        if not isinstance(date_input, datetime):
            # It's a date object
            return f"{date_input.year:04d}-{date_input.month:02d}-{date_input.day:02d}"

    if isinstance(date_input, str):
        # Try multiple date formats
        date_formats = [
            "%Y-%m-%d",      # 2024-01-15
            "%m/%d/%Y",      # 01/15/2024
            "%d-%m-%Y",      # 15-01-2024
        ]

        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_input, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # If no format matched, raise error
        raise ValueError(f"Invalid date format: {date_input}. Expected YYYY-MM-DD, MM/DD/YYYY, or DD-MM-YYYY")

    elif isinstance(date_input, datetime):
        return date_input.strftime("%Y-%m-%d")

    elif isinstance(date_input, int):
        # Assume it's a Unix timestamp
        dt = datetime.fromtimestamp(date_input)
        return dt.strftime("%Y-%m-%d")

    else:
        raise ValueError(f"Date must be string, datetime, date object, or timestamp, got {type(date_input)}")


# ============================================================================
# API Request Functions
# ============================================================================

def _make_fred_request(
    series_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    **kwargs
) -> pd.DataFrame:
    """
    Make FRED API request with retry logic and exponential backoff.

    This function wraps the fredapi library with retry logic to handle
    transient network errors. It attempts up to 3 retries with exponential
    backoff (1s, 2s, 4s delays).

    Args:
        series_id: FRED series ID (e.g., 'FEDFUNDS', 'DGS10')
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)
        **kwargs: Additional parameters to pass to fredapi

    Returns:
        pd.DataFrame: FRED series data with 'date' and 'value' columns

    Raises:
        FredRateLimitError: If API rate limit is exceeded
        FredInvalidSeriesError: If series ID is invalid or not found
        Exception: For other API errors after exhausting retries
    """
    if Fred is None:
        raise ImportError("fredapi package is not installed. Install with: pip install fredapi")

    # Validate series_id
    if not series_id or not isinstance(series_id, str):
        raise ValueError("series_id must be a non-empty string")

    # Get API key
    api_key = get_api_key()

    # Format dates if provided
    formatted_start = format_date_for_fred(start_date) if start_date else None
    formatted_end = format_date_for_fred(end_date) if end_date else None

    # Extract parameters from kwargs
    max_retries = kwargs.pop('max_retries', 3)
    use_cache = kwargs.pop('use_cache', False)
    base_delay = 1.0

    # Check cache first if enabled
    if use_cache:
        cached_data = _load_from_cache(series_id, start_date, end_date)
        if cached_data is not None:
            return cached_data

    # Initial attempt + retries
    for attempt in range(max_retries + 1):
        try:
            # Create FRED client
            fred = Fred(api_key=api_key)

            # Make API request
            series_data = fred.get_series(
                series_id,
                observation_start=formatted_start,
                observation_end=formatted_end,
                **kwargs
            )

            # Convert to DataFrame with standard column names
            # Handle both Series (real fredapi) and DataFrame (mocked in tests)
            if isinstance(series_data, pd.Series):
                df = pd.DataFrame({
                    'date': series_data.index,
                    'value': series_data.values
                })
            elif isinstance(series_data, pd.DataFrame):
                # Already a DataFrame (from mock), return as-is
                df = series_data
            else:
                raise ValueError(f"Unexpected return type from Fred API: {type(series_data)}")

            # Save to cache if enabled
            if use_cache:
                _save_to_cache(series_id, df, start_date, end_date)

            return df

        except Exception as e:
            error_msg = str(e).lower()

            # Check for rate limit errors
            if any(indicator in error_msg for indicator in [
                'rate limit', 'too many requests', 'rate_limit', 'ratelimit', '429'
            ]):
                raise FredRateLimitError(f"FRED API rate limit exceeded: {e}")

            # Check for invalid series errors
            if any(indicator in error_msg for indicator in [
                'bad request', 'not found', 'invalid series', 'series does not exist', '400', '404'
            ]):
                raise FredInvalidSeriesError(f"Invalid FRED series ID '{series_id}': {e}")

            # If this was the last attempt, raise the original exception
            if attempt >= max_retries:
                raise

            # Exponential backoff: 2^attempt seconds
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)

    # Should never reach here, but just in case
    raise Exception("Retry logic failed unexpectedly")


# ============================================================================
# Cache Management
# ============================================================================

def _get_cache_path(series_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Path:
    """
    Generate cache file path for FRED series data.

    Args:
        series_id: FRED series ID
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)

    Returns:
        Path: Cache file path
    """
    # Create filename with series ID and date range
    if start_date or end_date:
        filename_parts = [series_id]
        if start_date:
            filename_parts.append(start_date)
        if end_date:
            filename_parts.append(end_date)
        filename = "_".join(filename_parts) + ".parquet"
    else:
        filename = f"{series_id}.parquet"

    return CACHE_DIR / filename


def _load_from_cache(series_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None, cache_ttl_hours: Optional[int] = None) -> Optional[pd.DataFrame]:
    """
    Load FRED data from cache if available and not expired.

    Cache files are considered valid for cache_ttl_hours (default: CACHE_TTL_HOURS = 24 hours).

    Args:
        series_id: FRED series ID
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)
        cache_ttl_hours: Cache TTL in hours (optional, defaults to CACHE_TTL_HOURS)

    Returns:
        pd.DataFrame if cache is valid, None if cache is invalid or expired
    """
    cache_path = _get_cache_path(series_id, start_date, end_date)

    if not cache_path.exists():
        return None

    # Use provided TTL or default
    ttl_hours = cache_ttl_hours if cache_ttl_hours is not None else CACHE_TTL_HOURS

    # Check cache age
    cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
    if cache_age > timedelta(hours=ttl_hours):
        return None

    try:
        # Load cached data
        df = pd.read_parquet(cache_path)

        # Convert date column to datetime if not already
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])

        return df
    except Exception:
        # If cache is corrupted, return None
        return None


def _save_to_cache(series_id: str, data: pd.DataFrame, start_date: Optional[str] = None, end_date: Optional[str] = None) -> None:
    """
    Save FRED data to cache.

    Args:
        series_id: FRED series ID
        data: DataFrame to cache
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)
    """
    cache_path = _get_cache_path(series_id, start_date, end_date)

    # Ensure cache directory exists
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    # Save to parquet
    data.to_parquet(cache_path, index=False)
