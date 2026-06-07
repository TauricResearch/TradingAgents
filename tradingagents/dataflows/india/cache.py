"""Small cache helpers for respectful India data access."""

from __future__ import annotations

import hashlib
from pathlib import Path

from tradingagents.dataflows.india.symbols import safe_india_ticker_component


def india_cache_dir(base_dir: str | Path) -> Path:
    path = Path(base_dir) / "india"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_key(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def symbol_cache_path(base_dir: str | Path, symbol: str, name: str) -> Path:
    safe_symbol = safe_india_ticker_component(symbol)
    directory = india_cache_dir(base_dir) / safe_symbol
    directory.mkdir(parents=True, exist_ok=True)
    return directory / name
