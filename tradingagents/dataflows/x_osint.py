"""X (Twitter) OSINT vendor — most fragile signal source.

Uses the official X API v2 (tweepy.Client) via a paid bearer token. Treat
the output as a soft signal, never ground truth.

Required env: ``X_BEARER_TOKEN``.

NOTE: Skeleton; raise DataVendorError on missing token or rate-limit so the
analyst degrades gracefully. Scraping fallbacks are intentionally NOT
implemented (ToS risk + chronic breakage); pay for the API or skip.
"""

import os

from .errors import DataVendorError


def get_x_signals(query: str, start_date: str, end_date: str) -> str:
    """Recent-search via X API v2; returns dated digest with engagement metrics."""
    token = os.environ.get("X_BEARER_TOKEN")
    if not token:
        raise DataVendorError("X_BEARER_TOKEN not set")
    raise DataVendorError("x_osint.get_x_signals: implementation pending")
