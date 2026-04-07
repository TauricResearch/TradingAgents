from __future__ import annotations

import requests

from .api_keys import get_api_key
from .config import get_config
from .vendor_exceptions import VendorConfigurationError, VendorTransientError


_ECOS_API_BASE = "https://ecos.bok.or.kr/api"


def get_macro_news_ecos(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 10,
    region: str | None = None,
    language: str | None = None,
) -> str:
    api_key = get_api_key("ECOS_API_KEY")
    if not api_key:
        raise VendorConfigurationError("ECOS API key is not configured.")

    series = get_config().get("ecos_series", [])
    if not series:
        raise VendorConfigurationError("ECOS series configuration is missing.")

    try:
        response = requests.get(
            f"{_ECOS_API_BASE}/StatisticSearch/{api_key}/json/kr/1/{limit}",
            timeout=float(get_config().get("vendor_timeout", 15)),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise VendorTransientError(f"ECOS request failed: {exc}") from exc

    return (
        "ECOS macro adapter is configured but requires project-specific series codes. "
        "Provide `ecos_series` in config to enable Korean macro summaries."
    )
