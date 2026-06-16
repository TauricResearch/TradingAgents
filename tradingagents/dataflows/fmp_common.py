import os

import requests

from .errors import VendorNotConfiguredError, VendorRateLimitError


API_BASE_URL = "https://financialmodelingprep.com/stable"


class FMPNotConfiguredError(VendorNotConfiguredError):
    pass


class FMPRateLimitError(VendorRateLimitError):
    pass


def get_api_key() -> str:
    api_key = os.getenv("FMP_API_KEY") or os.getenv("FINANCIAL_MODELING_PREP_API_KEY")
    if not api_key:
        raise FMPNotConfiguredError(
            "FMP_API_KEY environment variable is not set."
        )
    return api_key


def make_request(endpoint: str, params: dict):
    api_params = params.copy()
    api_params["apikey"] = get_api_key()
    url = f"{API_BASE_URL}/{endpoint.lstrip('/')}"
    response = requests.get(url, params=api_params, timeout=30)
    response.raise_for_status()
    payload = response.json()

    if isinstance(payload, dict):
        message = str(payload.get("Error Message") or payload.get("message") or "")
        if any(marker in message.lower() for marker in ("limit", "invalid api key", "upgrade")):
            raise FMPRateLimitError(message)
    return payload
