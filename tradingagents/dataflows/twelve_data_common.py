import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from io import StringIO

from .alpha_vantage_common import AlphaVantageRateLimitError

API_BASE_URL = "https://api.twelvedata.com"

# Rate limit: 8 requests per minute for free tier
_MIN_REQUEST_INTERVAL = 8.0  # seconds between requests per key

# Per-key rate limiting: maps key suffix -> last request timestamp
_key_last_request: dict[str, float] = {}
_api_keys: list[str] = []
_current_key_idx = 0


def _load_api_keys():
    """Load API keys from env (comma-separated for rotation)."""
    global _api_keys
    if _api_keys:
        return
    raw = os.getenv("TWELVE_DATA_API_KEY", "")
    _api_keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not _api_keys:
        raise ValueError("TWELVE_DATA_API_KEY environment variable is not set.")


def _pick_key() -> str:
    """Pick the API key with the longest idle time (round-robin with smart selection)."""
    _load_api_keys()
    if len(_api_keys) == 1:
        return _api_keys[0]

    now = time.time()
    best_key = None
    best_idle = -1

    for key in _api_keys:
        suffix = key[-6:]
        last = _key_last_request.get(suffix, 0)
        idle = now - last
        if idle > best_idle:
            best_idle = idle
            best_key = key

    return best_key


def _rate_limit_throttle(key: str):
    """Ensure minimum interval per API key."""
    suffix = key[-6:]
    now = time.time()
    last = _key_last_request.get(suffix, 0)
    elapsed = now - last
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _key_last_request[suffix] = time.time()


class TwelveDataRateLimitError(AlphaVantageRateLimitError):
    """Twelve Data rate limit error. Inherits from AlphaVantageRateLimitError
    so the existing fallback mechanism in interface.py catches it automatically."""
    pass


def get_api_key() -> str:
    """Retrieve the best available API key (round-robin across multiple keys)."""
    return _pick_key()


def _make_api_request(endpoint: str, params: dict = None) -> dict:
    """Make an API request to Twelve Data.

    Raises:
        TwelveDataRateLimitError: When rate limit is exceeded or endpoint not found.
    """
    if params is None:
        params = {}
    api_key = get_api_key()
    params["apikey"] = api_key

    _rate_limit_throttle(api_key)

    url = f"{API_BASE_URL}/{endpoint}"
    response = requests.get(url, params=params)

    # 404 means endpoint not available on this plan
    if response.status_code == 404:
        raise TwelveDataRateLimitError(
            f"Twelve Data endpoint '{endpoint}' not available. Falling back."
        )

    response.raise_for_status()

    data = response.json()

    # Twelve Data returns errors in the JSON body
    if isinstance(data, dict):
        status = data.get("status")
        if status == "error":
            message = data.get("message", "")
            if "rate limit" in message.lower() or "api credits" in message.lower() or data.get("code") == 429:
                raise TwelveDataRateLimitError(
                    f"Twelve Data rate limit exceeded: {message}"
                )
            # Other API errors - also raise to trigger fallback
            raise TwelveDataRateLimitError(f"Twelve Data API error: {message}")

    return data


def _calc_start_date(curr_date: str, look_back_days: int) -> str:
    """Calculate start date from curr_date minus look_back_days."""
    dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start = dt - timedelta(days=int(look_back_days * 1.5))  # extra buffer for weekends/holidays
    return start.strftime("%Y-%m-%d")


def _filter_csv_by_date_range(csv_data: str, start_date: str, end_date: str) -> str:
    """Filter CSV data to include only rows within the specified date range."""
    if not csv_data or csv_data.strip() == "":
        return csv_data
    try:
        df = pd.read_csv(StringIO(csv_data))
        date_col = df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col])
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        filtered = df[(df[date_col] >= start_dt) & (df[date_col] <= end_dt)]
        return filtered.to_csv(index=False)
    except Exception:
        return csv_data
