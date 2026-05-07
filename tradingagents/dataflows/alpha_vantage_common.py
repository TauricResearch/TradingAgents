import logging
import os
import re
import requests
import pandas as pd
import json
from datetime import datetime
from io import StringIO

logger = logging.getLogger(__name__)

API_BASE_URL = "https://www.alphavantage.co/query"

# Connect / read timeout for outbound HTTP. Without this, a stuck Alpha
# Vantage backend will hang the entire analysis run.
HTTP_TIMEOUT = (5, 30)


def get_api_key() -> str:
    """Retrieve the API key for Alpha Vantage from environment variables."""
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise ValueError("ALPHA_VANTAGE_API_KEY environment variable is not set.")
    return api_key


def _redact_api_key(message: str) -> str:
    """Replace the literal apikey value in any string with [REDACTED].

    requests.HTTPError stringifies with the full URL including query params,
    which leaks the Alpha Vantage api key into logs and exception traces.
    Use this on any error message before logging or re-raising.
    """
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    # Also redact any apikey=... pattern in case the env var value differs
    return re.sub(r"apikey=[^&\s]+", "apikey=[REDACTED]", message)

def format_datetime_for_api(date_input) -> str:
    """Convert various date formats to YYYYMMDDTHHMM format required by Alpha Vantage API."""
    if isinstance(date_input, str):
        # If already in correct format, return as-is
        if len(date_input) == 13 and 'T' in date_input:
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
    elif isinstance(date_input, datetime):
        return date_input.strftime("%Y%m%dT%H%M")
    else:
        raise ValueError(f"Date must be string or datetime object, got {type(date_input)}")

class AlphaVantageRateLimitError(Exception):
    """Exception raised when Alpha Vantage API rate limit is exceeded."""
    pass

def _make_api_request(function_name: str, params: dict) -> dict | str:
    """Helper function to make API requests and handle responses.
    
    Raises:
        AlphaVantageRateLimitError: When API rate limit is exceeded
    """
    # Create a copy of params to avoid modifying the original
    api_params = params.copy()
    api_params.update({
        "function": function_name,
        "apikey": get_api_key(),
        "source": "trading_agents",
    })
    
    # Handle entitlement parameter if present in params or global variable
    current_entitlement = globals().get('_current_entitlement')
    entitlement = api_params.get("entitlement") or current_entitlement
    
    if entitlement:
        api_params["entitlement"] = entitlement
    elif "entitlement" in api_params:
        # Remove entitlement if it's None or empty
        api_params.pop("entitlement", None)
    
    try:
        response = requests.get(API_BASE_URL, params=api_params, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
    except requests.HTTPError as e:
        # requests.HTTPError stringifies with the full URL — scrub the api
        # key before re-raising so it doesn't leak via uncaught exceptions.
        scrubbed = _redact_api_key(str(e))
        raise requests.HTTPError(scrubbed) from None
    except requests.RequestException as e:
        scrubbed = _redact_api_key(str(e))
        raise requests.RequestException(scrubbed) from None

    response_text = response.text

    # Check if response is JSON (error responses are typically JSON)
    try:
        response_json = json.loads(response_text)
        # Check for rate limit error
        if "Information" in response_json:
            info_message = response_json["Information"]
            if "rate limit" in info_message.lower() or "api key" in info_message.lower():
                raise AlphaVantageRateLimitError(f"Alpha Vantage rate limit exceeded: {info_message}")
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
        logger.warning("Failed to filter CSV data by date range: %s", e)
        return csv_data
