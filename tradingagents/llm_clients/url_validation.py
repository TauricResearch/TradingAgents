"""URL validation helpers for configurable LLM endpoints."""

from __future__ import annotations

from urllib.parse import urlsplit


def validate_custom_provider_base_url(url: str | None) -> str:
    """Return a safe custom-provider base URL or raise ``ValueError``.

    Custom provider URLs are printed in CLI output, so credentials embedded
    in the URL must be rejected instead of accidentally logged.
    """
    value = (url or "").strip()
    if not value:
        raise ValueError(
            "Custom provider requires TRADINGAGENTS_LLM_BACKEND_URL "
            "or config['backend_url'] to be set."
        )

    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(
            "Custom provider backend URL must start with http:// or https:// "
            "and include a host."
        )

    if parsed.username or parsed.password:
        raise ValueError(
            "Custom provider backend URL must not include embedded credentials. "
            "Use CUSTOM_PROVIDER_API_KEY for authentication."
        )

    return value
