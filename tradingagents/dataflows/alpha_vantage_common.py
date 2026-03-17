import os
import requests
import pandas as pd
import json
import threading
import time as _time
from datetime import datetime
from io import StringIO

API_BASE_URL = "https://www.alphavantage.co/query"

def get_api_key() -> str:
    """Retrieve the API key for Alpha Vantage from environment variables."""
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise ValueError("ALPHA_VANTAGE_API_KEY environment variable is not set.")
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
                raise ValueError(f"Unsupported date format: {date_input}")
    elif isinstance(date_input, datetime):
        return date_input.strftime("%Y%m%dT%H%M")
    else:
        raise ValueError(f"Date must be string or datetime object, got {type(date_input)}")

# ─── Exception hierarchy ─────────────────────────────────────────────────────

class AlphaVantageError(Exception):
    """Base exception for all Alpha Vantage API errors."""
    pass


class APIKeyInvalidError(AlphaVantageError):
    """Raised when the API key is invalid or missing (401-equivalent)."""
    pass


class RateLimitError(AlphaVantageError):
    """Raised when the API rate limit is exceeded (429-equivalent)."""
    pass


# Keep old name as alias so existing imports don't break
AlphaVantageRateLimitError = RateLimitError


class ThirdPartyError(AlphaVantageError):
    """Raised on server-side errors (5xx status codes)."""
    pass


class ThirdPartyTimeoutError(AlphaVantageError):
    """Raised when the request times out."""
    pass


class ThirdPartyParseError(AlphaVantageError):
    """Raised when the response cannot be parsed (malformed JSON/CSV)."""
    pass


# ─── Rate-limited request helper ─────────────────────────────────────────────


_rate_lock = threading.Lock()
_call_timestamps: list[float] = []
_RATE_LIMIT = 75  # calls per minute (Alpha Vantage premium)


def _rate_limited_request(function_name: str, params: dict, timeout: int = 30) -> dict | str:
    """Make an API request with rate limiting (75 calls/min for premium key)."""
    sleep_time = 0.0
    with _rate_lock:
        now = _time.time()
        # Remove timestamps older than 60 seconds
        _call_timestamps[:] = [t for t in _call_timestamps if now - t < 60]
        if len(_call_timestamps) >= _RATE_LIMIT:
            sleep_time = 60 - (now - _call_timestamps[0]) + 0.1

    # Sleep outside the lock to avoid blocking other threads
    if sleep_time > 0:
        _time.sleep(sleep_time)

    # Re-check and register under lock to avoid races where multiple
    # threads calculate similar sleep times and then all fire at once.
    while True:
        with _rate_lock:
            now = _time.time()
            _call_timestamps[:] = [t for t in _call_timestamps if now - t < 60]
            if len(_call_timestamps) >= _RATE_LIMIT:
                # Another thread filled the window while we slept — wait again
                extra_sleep = 60 - (now - _call_timestamps[0]) + 0.1
            else:
                _call_timestamps.append(_time.time())
                break
        # Sleep outside the lock to avoid blocking other threads
        _time.sleep(extra_sleep)


    return _make_api_request(function_name, params, timeout=timeout)


# ─── Core API request ────────────────────────────────────────────────────────

def _make_api_request(function_name: str, params: dict, timeout: int = 30) -> dict | str:
    """Make an Alpha Vantage API request with proper error handling.

    Returns the response text (JSON string or CSV).

    Raises:
        APIKeyInvalidError: Invalid or missing API key.
        RateLimitError: Rate limit exceeded.
        ThirdPartyError: Server-side error (5xx).
        ThirdPartyTimeoutError: Request timed out.
        ThirdPartyParseError: Response could not be parsed.
    """
    api_params = params.copy()
    api_params.update({
        "function": function_name,
        "apikey": get_api_key(),
        "source": "trading_agents",
    })

    # Handle entitlement parameter
    current_entitlement = globals().get('_current_entitlement')
    entitlement = api_params.get("entitlement") or current_entitlement
    if entitlement:
        api_params["entitlement"] = entitlement
    else:
        api_params.pop("entitlement", None)

    try:
        response = requests.get(API_BASE_URL, params=api_params, timeout=timeout)
    except requests.exceptions.Timeout:
        raise ThirdPartyTimeoutError(
            f"Request timed out: function={function_name}, params={params}"
        )
    except requests.exceptions.ConnectionError as exc:
        raise ThirdPartyError(f"Connection error: function={function_name}, error={exc}")
    except requests.exceptions.RequestException as exc:
        raise ThirdPartyError(f"Request failed: function={function_name}, error={exc}")

    # HTTP-level errors
    if response.status_code == 401:
        raise APIKeyInvalidError(
            f"Invalid API key: status={response.status_code}, body={response.text[:200]}"
        )
    if response.status_code == 429:
        raise RateLimitError(
            f"Rate limit exceeded: status={response.status_code}, body={response.text[:200]}"
        )
    if response.status_code >= 500:
        raise ThirdPartyError(
            f"Server error: status={response.status_code}, function={function_name}, "
            f"body={response.text[:200]}"
        )
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raise ThirdPartyError(
            f"HTTP error: status={response.status_code}, function={function_name}, "
            f"body={response.text[:200]}"
        ) from exc

    response_text = response.text

    # Check for AV-specific error patterns in JSON body
    try:
        response_json = json.loads(response_text)

        if "Error Message" in response_json:
            msg = response_json["Error Message"]
            if "invalid" in msg.lower() and "apikey" in msg.lower():
                raise APIKeyInvalidError(f"Alpha Vantage: {msg}")
            raise AlphaVantageError(f"Alpha Vantage API error: {msg}")

        if "Information" in response_json:
            info = response_json["Information"]
            info_lower = info.lower()
            if "rate limit" in info_lower or "call frequency" in info_lower:
                raise RateLimitError(f"Alpha Vantage rate limit: {info}")
            if "invalid" in info_lower and "api" in info_lower:
                raise APIKeyInvalidError(f"Alpha Vantage: {info}")

        if "Note" in response_json:
            note = response_json["Note"]
            if "api call frequency" in note.lower() or "rate limit" in note.lower():
                raise RateLimitError(f"Alpha Vantage rate limit: {note}")

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
