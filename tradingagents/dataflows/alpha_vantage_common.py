import json
import os
import time
from datetime import datetime
from io import StringIO

import pandas as pd
import requests

API_BASE_URL = "https://www.alphavantage.co/query"
AV_REQUEST_TIMEOUT = 15
AV_MAX_RETRIES = 3
AV_BACKOFF_BASE = 1.5


class AlphaVantageNotConfiguredError(ValueError):
    """Raised when Alpha Vantage is selected but no API key is configured.

    Subclasses ValueError for backward compatibility with callers that
    already catch ValueError, while letting the routing layer distinguish a
    "vendor unavailable" condition from a genuine data error.
    """

    pass


class AlphaVantageRateLimitError(Exception):
    """Raised when Alpha Vantage API rate limit is exceeded."""

    pass


class AlphaVantageAuthError(ValueError):
    """Raised when Alpha Vantage rejects the configured API key."""

    pass


def get_api_key() -> str:
    """Retrieve the API key for Alpha Vantage from environment variables."""
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise AlphaVantageNotConfiguredError(
            "ALPHA_VANTAGE_API_KEY environment variable is not set."
        )
    return api_key


def format_datetime_for_api(date_input) -> str:
    """Convert various date formats to YYYYMMDDTHHMM required by Alpha Vantage."""
    if isinstance(date_input, str):
        # If already in correct format, return as-is
        if len(date_input) == 13 and "T" in date_input:
            return date_input
        # Try to parse common date formats
        try:
            dt = datetime.strptime(date_input, "%Y-%m-%d")
            return dt.strftime("%Y%m%dT0000")
        except ValueError:
            try:
                dt = datetime.strptime(date_input, "%Y-%m-%d %H:%M")
                return dt.strftime("%Y%m%dT%H%M")
            except ValueError:
                raise ValueError(f"Unsupported date format: {date_input}")
    if isinstance(date_input, datetime):
        return date_input.strftime("%Y%m%dT%H%M")
    raise ValueError(f"Date must be string or datetime object, got {type(date_input)}")


def _get_with_retry(params: dict) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(AV_MAX_RETRIES):
        try:
            response = requests.get(
                API_BASE_URL,
                params=params,
                timeout=AV_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            last_exc = exc
            if attempt < AV_MAX_RETRIES - 1:
                time.sleep(AV_BACKOFF_BASE * (2**attempt))
    assert last_exc is not None
    raise last_exc


def _classify_information_message(info_message: str) -> None:
    msg = info_message.lower()
    if "rate limit" in msg or "frequency" in msg or "call frequency" in msg:
        raise AlphaVantageRateLimitError(
            f"Alpha Vantage rate limit exceeded: {info_message}"
        )
    if "api key" in msg or "apikey" in msg or "invalid key" in msg:
        raise AlphaVantageAuthError(f"Alpha Vantage API key rejected: {info_message}")


def _make_api_request(function_name: str, params: dict) -> dict | str:
    """Make an Alpha Vantage request with timeout, retry, and error typing.

    Raises:
        AlphaVantageRateLimitError: when vendor quota/frequency limit is hit.
        AlphaVantageAuthError: when the configured API key is invalid/rejected.
        requests.RequestException: when transport fails after bounded retries.
    """
    # Create a copy of params to avoid modifying the original
    api_params = params.copy()
    api_params.update(
        {
            "function": function_name,
            "apikey": get_api_key(),
            "source": "trading_agents",
        }
    )

    # Keep entitlement explicit: callers may pass params["entitlement"], but
    # there is no hidden global entitlement side channel.
    if not api_params.get("entitlement"):
        api_params.pop("entitlement", None)

    response = _get_with_retry(api_params)
    response_text = response.text

    # Check if response is JSON (error responses are typically JSON)
    try:
        response_json = json.loads(response_text)
        if "Information" in response_json:
            _classify_information_message(response_json["Information"])
        if "Error Message" in response_json:
            message = response_json["Error Message"]
            if "api key" in message.lower() or "apikey" in message.lower():
                raise AlphaVantageAuthError(f"Alpha Vantage API key rejected: {message}")
    except json.JSONDecodeError:
        # Response is not JSON (likely CSV data), which is normal
        pass

    return response_text


def _filter_csv_by_date_range(csv_data: str, start_date: str, end_date: str) -> str:
    """
    Filter CSV data to include only rows within the specified date range.

    Args:
        csv_data: CSV string from Alpha Vantage API
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        Filtered CSV string
    """
    if not csv_data or csv_data.strip() == "":
        return csv_data

    try:
        # Parse CSV data
        df = pd.read_csv(StringIO(csv_data))

        # Assume the first column is the date column (timestamp)
        date_col = df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col])

        # Filter by date range
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)

        filtered_df = df[(df[date_col] >= start_dt) & (df[date_col] <= end_dt)]

        # Convert back to CSV string
        return filtered_df.to_csv(index=False)

    except Exception as e:
        # If filtering fails, return original data with a warning
        print(f"Warning: Failed to filter CSV data by date range: {e}")
        return csv_data
