import os

import requests

from .errors import VendorNotConfiguredError, VendorRateLimitError


API_BASE_URL = "https://finnhub.io/api/v1"


class FinnhubNotConfiguredError(VendorNotConfiguredError):
    pass


class FinnhubRateLimitError(VendorRateLimitError):
    pass


def get_api_key() -> str:
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise FinnhubNotConfiguredError(
            "FINNHUB_API_KEY environment variable is not set."
        )
    return api_key


def make_request(endpoint: str, params: dict):
    api_params = params.copy()
    api_params["token"] = get_api_key()
    url = f"{API_BASE_URL}/{endpoint.lstrip('/')}"
    response = requests.get(url, params=api_params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        message = str(payload.get("error") or "")
        if any(marker in message.lower() for marker in ("limit", "premium", "token")):
            raise FinnhubRateLimitError(message)
    return payload
