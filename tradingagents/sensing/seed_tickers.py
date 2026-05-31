"""Seed the `tickers` reference table.

Two sources:
  - Polygon /v3/reference/tickers (paginated, free on dev tier) for US equities.
  - tradingagents/sensing/data/crypto_universe.yaml for top-20 crypto.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import requests
import yaml

from tradingagents.persistence.store import upsert_ticker


_POLYGON_BASE = "https://api.polygon.io/v3/reference/tickers"


# Polygon exchange mics → our short labels.
_EXCHANGE_MAP = {
    "XNAS": "NASDAQ",
    "XNYS": "NYSE",
    "ARCX": "ARCA",
    "BATS": "BATS",
}


def _crypto_path() -> Path:
    return Path(__file__).parent / "data" / "crypto_universe.yaml"


def seed_crypto(conn: sqlite3.Connection) -> int:
    """Upsert all crypto entries from the static YAML. Returns row count."""
    items = yaml.safe_load(_crypto_path().read_text())
    n = 0
    for item in items:
        upsert_ticker(
            conn,
            ticker=item["ticker"],
            exchange="CRYPTO",
            name=item["name"],
            aliases=item.get("aliases", []),
            active=True,
        )
        n += 1
    return n


def _polygon_get(url: str, *, api_key: str, max_retries: int) -> dict:
    """GET one Polygon page, retrying HTTP 429 (free-tier rate limit).

    Honors the ``Retry-After`` response header when present; otherwise backs
    off 15s, 30s, then 60s. Other HTTP errors raise immediately.
    """
    attempt = 0
    while True:
        r = requests.get(url, params={"apiKey": api_key}, timeout=30)
        if r.status_code == 429 and attempt < max_retries:
            retry_after = r.headers.get("Retry-After")
            try:
                wait = float(retry_after) if retry_after else 0.0
            except ValueError:
                wait = 0.0
            if wait <= 0:
                wait = min(60.0, 15.0 * (2 ** attempt))
            attempt += 1
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()


def seed_polygon(
    conn: sqlite3.Connection,
    *,
    market: str = "stocks",
    throttle_s: float | None = None,
    max_retries: int | None = None,
) -> int:
    """Walk the paginated Polygon reference endpoint. Returns row count.

    Polygon's free/dev tier allows ~5 requests/minute and the reference
    endpoint paginates (~5-6 pages for US stocks at limit=1000), so we sleep
    ``throttle_s`` between pages and retry HTTP 429 (see ``_polygon_get``).
    Defaults are free-tier-safe; tune via the POLYGON_SEED_THROTTLE_S /
    POLYGON_SEED_MAX_RETRIES env vars (e.g. throttle 0 on a paid tier).
    """
    api_key = os.environ.get("POLYGON_API_KEY")
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY required for seed_polygon()")
    if throttle_s is None:
        throttle_s = float(os.environ.get("POLYGON_SEED_THROTTLE_S", "13"))
    if max_retries is None:
        max_retries = int(os.environ.get("POLYGON_SEED_MAX_RETRIES", "6"))

    url = f"{_POLYGON_BASE}?market={market}&active=true&limit=1000"
    n = 0
    first = True
    while url:
        # Proactively throttle between pages (not before the first) to stay
        # under the free-tier rate limit; 429s are still retried defensively.
        if not first and throttle_s > 0:
            time.sleep(throttle_s)
        first = False
        data = _polygon_get(url, api_key=api_key, max_retries=max_retries)
        for item in data.get("results", []):
            exch_mic = item.get("primary_exchange", "")
            upsert_ticker(
                conn,
                ticker=item["ticker"],
                exchange=_EXCHANGE_MAP.get(exch_mic, exch_mic or "UNKNOWN"),
                name=item.get("name", ""),
                aliases=[],
                active=bool(item.get("active", True)),
            )
            n += 1
        next_url = data.get("next_url")
        url = next_url if next_url else None
    return n


def seed_all(conn: sqlite3.Connection) -> dict:
    """Seed both. Returns {'crypto': n, 'polygon': n}."""
    return {
        "crypto": seed_crypto(conn),
        "polygon": seed_polygon(conn),
    }
