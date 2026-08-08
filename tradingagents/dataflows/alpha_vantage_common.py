import json
import os
from datetime import datetime
from io import StringIO

import pandas as pd
import requests

from tradingagents.logging_utils import safe_exception_type

from .errors import VendorError, VendorNotConfiguredError, VendorRateLimitError

API_BASE_URL = "https://www.alphavantage.co/query"

# Network timeout (seconds) so a stalled Alpha Vantage request can't hang the
# CLI/agents indefinitely (#990).
REQUEST_TIMEOUT = 30


class AlphaVantageNotConfiguredError(VendorNotConfiguredError):
    """Raised when Alpha Vantage is selected but no API key is configured.

    A VendorNotConfiguredError (and thus still a ValueError), so the routing
    layer's "vendor unavailable" handling and existing ValueError callers both
    keep working.
    """
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
                raise ValueError(f"Unsupported date format: {date_input}") from None
    elif isinstance(date_input, datetime):
        return date_input.strftime("%Y%m%dT%H%M")
    else:
        raise ValueError(f"Date must be string or datetime object, got {type(date_input)}")

class AlphaVantageRateLimitError(VendorRateLimitError):
    """Raised when the Alpha Vantage API rate limit is exceeded."""
    pass


class AlphaVantageDataError(VendorError):
    """Raised when an Alpha Vantage response cannot be used safely."""


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
        response = requests.get(
            API_BASE_URL, params=api_params, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise AlphaVantageDataError(
            f"Alpha Vantage request failed ({safe_exception_type(exc)})"
        ) from None

    try:
        response_text = response.text
    except Exception as exc:
        raise AlphaVantageDataError(
            f"Alpha Vantage response could not be read ({safe_exception_type(exc)})"
        ) from None

    # Error responses are JSON; data responses are usually CSV (or data-keyed
    # JSON). A non-JSON body is normal data.
    try:
        response_json = json.loads(response_text)
    except json.JSONDecodeError:
        return response_text
    if not isinstance(response_json, dict):
        raise AlphaVantageDataError("Alpha Vantage response was not a JSON object")

    # Alpha Vantage reports problems via "Information" / "Note". Classify so a
    # genuine rate limit and an invalid/missing key aren't conflated (#991):
    # rate-limit phrasing is checked first because those notices also mention
    # "API key" ("your API key ... 25 requests per day").
    has_notice = "Information" in response_json or "Note" in response_json
    notice = response_json.get("Information") or response_json.get("Note")
    if has_notice:
        if not isinstance(notice, str) or not notice.strip():
            raise AlphaVantageDataError("Alpha Vantage returned an unusable notice")
        low = notice.lower()
        if any(m in low for m in ("rate limit", "requests per day", "call frequency", "premium")):
            raise AlphaVantageRateLimitError("Alpha Vantage rate limit exceeded")
        if "api key" in low or "apikey" in low:
            # Reuse the existing "not configured" error so a bad key surfaces as
            # a real, actionable failure rather than a mislabeled rate limit (#991).
            raise AlphaVantageNotConfiguredError(
                "Alpha Vantage API key is invalid or missing"
            )
        raise AlphaVantageDataError("Alpha Vantage returned an unusable notice")
    if response_json.get("Error Message"):
        raise AlphaVantageDataError("Alpha Vantage rejected the request")

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
    try:
        if not isinstance(csv_data, str):
            raise TypeError("CSV response is not text")
        if not csv_data.strip():
            return csv_data
        df = pd.read_csv(StringIO(csv_data))
        if df.columns.empty or df.columns[0] != "timestamp":
            raise ValueError("missing timestamp column")

        timestamps = pd.to_datetime(
            df["timestamp"], format="%Y-%m-%d", errors="raise"
        )
        start_dt = pd.Timestamp(datetime.strptime(start_date, "%Y-%m-%d"))
        end_dt = pd.Timestamp(datetime.strptime(end_date, "%Y-%m-%d"))
        if start_dt > end_dt:
            raise ValueError("start date is after end date")

        filtered_df = df[(timestamps >= start_dt) & (timestamps <= end_dt)]
        return filtered_df.to_csv(index=False)
    except Exception:
        raise AlphaVantageDataError(
            "Alpha Vantage CSV response could not be safely filtered"
        ) from None
