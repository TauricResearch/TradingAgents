"""
DEPRECATED — Alpha Vantage removed in the FMP-primary migration.

This module used to be the shared Alpha Vantage HTTP wrapper (API key
lookup + request sender + rate-limit handling). Every function is a
no-op stub now; callers through ``interface.py`` and the sibling
``alpha_vantage_*`` modules won't import-error, but every data call
returns an empty string / sentinel. Alpha Vantage free-tier (25 req/day)
was secondary fallback anyway; FMP Ultimate is authoritative.

Remove this file once no ``from .alpha_vantage_common import ...``
imports remain anywhere in the tree.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class AlphaVantageRateLimitError(Exception):
    """Kept for type-compat with any `except AlphaVantageRateLimitError` sites."""


def get_api_key() -> str:
    return ""


def format_datetime_for_api(date_input) -> str:
    # Pass-through of a date string is harmless; callers pass ISO dates.
    return str(date_input) if date_input is not None else ""


def _make_api_request(function_name: str, params: dict) -> dict | str:
    logger.debug("alpha_vantage call skipped (module stubbed): %s", function_name)
    return {}


def _filter_csv_by_date_range(csv_data: str, start_date: str, end_date: str) -> str:
    return csv_data or ""
