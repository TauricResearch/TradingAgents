"""Watchlist loader for the scheduled TradingAgents runner.

Reads the YAML file pointed to by ``TRADINGAGENTS_WATCHLIST_PATH``
(default ``config/watchlist.yaml``) and returns the list of tickers the
runner should iterate over.

The format is intentionally tiny so a non-developer can edit it by hand::

    tickers:
      - symbol: BTC-USD
        asset_type: crypto
      - symbol: NVDA
        asset_type: stock        # default if omitted

``analysts`` is optional and overrides the project's DEFAULT_CONFIG analyst
selection for that symbol only.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_WATCHLIST_PATH = "config/watchlist.yaml"

ENV_WATCHLIST_PATH = "TRADINGAGENTS_WATCHLIST_PATH"


@dataclass
class WatchlistEntry:
    symbol: str
    asset_type: str = "stock"
    analysts: list[str] | None = None  # None = use DEFAULT_CONFIG


def watchlist_path() -> Path:
    raw = os.environ.get(ENV_WATCHLIST_PATH, DEFAULT_WATCHLIST_PATH)
    return Path(raw)


def load_watchlist(path: Path | None = None) -> list[WatchlistEntry]:
    """Read and validate the watchlist file.

    Missing file is treated as an empty list with a warning — the scheduled
    run still completes with no work to do, which is preferable to failing.
    """
    target = Path(path) if path is not None else watchlist_path()
    if not target.exists():
        logger.warning("Watchlist file %s not found; runner will exit cleanly", target)
        return []

    raw = target.read_text(encoding="utf-8")
    payload = _parse_yaml(raw)
    entries_raw = payload.get("tickers", [])
    if not isinstance(entries_raw, list):
        raise ValueError(f"{target}: 'tickers' must be a list, got {type(entries_raw).__name__}")

    entries: list[WatchlistEntry] = []
    for index, item in enumerate(entries_raw):
        if not isinstance(item, dict):
            raise ValueError(f"{target}: tickers[{index}] must be a mapping, got {type(item).__name__}")
        if "symbol" not in item:
            raise ValueError(f"{target}: tickers[{index}] missing required 'symbol'")
        symbol = str(item["symbol"]).strip()
        if not symbol:
            raise ValueError(f"{target}: tickers[{index}] has empty 'symbol'")
        asset_type = str(item.get("asset_type", "stock")).strip().lower()
        if asset_type not in {"stock", "crypto"}:
            raise ValueError(
                f"{target}: tickers[{index}].asset_type must be 'stock' or 'crypto', got {asset_type!r}"
            )
        analysts_raw = item.get("analysts")
        analysts: list[str] | None = None
        if analysts_raw is not None:
            if not isinstance(analysts_raw, list) or not all(
                isinstance(a, str) for a in analysts_raw
            ):
                raise ValueError(
                    f"{target}: tickers[{index}].analysts must be a list of strings"
                )
            analysts = [a.strip() for a in analysts_raw if a.strip()]
        entries.append(WatchlistEntry(symbol=symbol, asset_type=asset_type, analysts=analysts))
    return entries


def _parse_yaml(raw: str) -> dict:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required to read the watchlist; "
            "install with `pip install tradingagents[scheduled]`"
        ) from exc
    data = yaml.safe_load(raw)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Watchlist root must be a mapping, got {type(data).__name__}")
    return data
