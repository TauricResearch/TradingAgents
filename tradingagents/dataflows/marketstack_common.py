import os

import requests

from .errors import VendorNotConfiguredError, VendorRateLimitError


API_BASE_URL = "https://api.marketstack.com/v1"


class MarketstackNotConfiguredError(VendorNotConfiguredError):
    pass


class MarketstackRateLimitError(VendorRateLimitError):
    pass


def get_api_key() -> str:
    api_key = os.getenv("MARKETSTACK_API_KEY")
    if not api_key:
        raise MarketstackNotConfiguredError(
            "MARKETSTACK_API_KEY environment variable is not set."
        )
    return api_key


def make_request(endpoint: str, params: dict):
    api_params = params.copy()
    api_params["access_key"] = get_api_key()
    url = f"{API_BASE_URL}/{endpoint.lstrip('/')}"
    response = requests.get(url, params=api_params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    error = payload.get("error") if isinstance(payload, dict) else None
    if error:
        message = str(error.get("message") or error)
        if any(marker in message.lower() for marker in ("limit", "access key", "plan")):
            raise MarketstackRateLimitError(message)
        raise ValueError(message)
    return payload
