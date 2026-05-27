"""Seed the `tickers` reference table.

Two sources:
  - Polygon /v3/reference/tickers (paginated, free on dev tier) for US equities.
  - tradingagents/sensing/data/crypto_universe.yaml for top-20 crypto.
"""

from __future__ import annotations

import os
import sqlite3
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


def seed_polygon(conn: sqlite3.Connection, *, market: str = "stocks") -> int:
    """Walk the paginated Polygon reference endpoint. Returns row count."""
    api_key = os.environ.get("POLYGON_API_KEY")
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY required for seed_polygon()")
    url = f"{_POLYGON_BASE}?market={market}&active=true&limit=1000"
    n = 0
    while url:
        r = requests.get(url, params={"apiKey": api_key}, timeout=30)
        r.raise_for_status()
        data = r.json()
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
