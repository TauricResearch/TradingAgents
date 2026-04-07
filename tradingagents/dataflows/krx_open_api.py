from __future__ import annotations

import requests

from .api_keys import get_api_key
from .config import get_config
from .vendor_exceptions import VendorConfigurationError, VendorTransientError


_KRX_API_BASE = "https://openapi.krx.co.kr"


def call_krx_open_api(api_path: str, params: dict[str, str] | None = None) -> dict:
    api_key = get_api_key("KRX_API_KEY")
    if not api_key:
        raise VendorConfigurationError("KRX Open API key is not configured.")

    try:
        response = requests.get(
            f"{_KRX_API_BASE.rstrip('/')}/{api_path.lstrip('/')}",
            params=params or {},
            headers={"AUTH_KEY": api_key},
            timeout=float(get_config().get("vendor_timeout", 15)),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise VendorTransientError(f"KRX Open API request failed: {exc}") from exc

    return response.json()
