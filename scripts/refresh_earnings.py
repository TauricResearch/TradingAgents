"""Refresh the confirmed earnings-date cache used by options automation."""

import argparse
import json
import logging
import os
import re
import sys
import tempfile
from collections.abc import Callable, Iterable
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tradingagents.default_config import DEFAULT_CONFIG

LOGGER = logging.getLogger(__name__)
SOURCE = "Wall Street Horizon"
USER_AGENT = "TradingAgents-Earnings-Refresh/1.0"
NEW_YORK = ZoneInfo("America/New_York")
WALL_STREET_HORIZON_PAGES = {
    "AAPL": "https://www.wallstreethorizon.com/aapl-earnings-calendar",
    "MSFT": "https://www.wallstreethorizon.com/msft-earnings-calendar",
    "NVDA": "https://www.wallstreethorizon.com/nvda-earnings-calendar",
    "AMZN": "https://www.wallstreethorizon.com/amzn-earnings-calendar",
    "META": "https://www.wallstreethorizon.com/meta-earnings-calendar",
    "GOOG": "https://www.wallstreethorizon.com/goog-earnings-calendar",
    "TSLA": "https://www.wallstreethorizon.com/tsla-earnings-calendar",
}
_CONFIRMED_DATE = re.compile(r"\bCONFIRMED\b(?:\s+for)?(?:\s+[A-Za-z]+)?\s+(\d{1,2}/\d{1,2}/\d{4})")


def fetch_page(symbol: str, *, open_url=urlopen) -> str:
    """Fetch one supported Wall Street Horizon company page."""
    try:
        url = WALL_STREET_HORIZON_PAGES[symbol]
    except KeyError as error:
        raise ValueError(f"unsupported earnings symbol: {symbol}") from error
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with open_url(request, 30) as response:
        return response.read().decode("utf-8")


def _future_confirmed_date(page: str, symbol: str, today: date) -> date:
    matches = _CONFIRMED_DATE.findall(page)
    parsed = []
    for value in matches:
        try:
            parsed.append(datetime.strptime(value, "%m/%d/%Y").date())
        except ValueError:
            continue
    if len(parsed) != 1 or parsed[0] <= today:
        raise ValueError(f"{symbol} must have one confirmed future earnings date")
    return parsed[0]


def _validated_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(str(symbol).strip().upper() for symbol in symbols)
    if (
        not normalized
        or len(normalized) != len(set(normalized))
        or any(symbol not in WALL_STREET_HORIZON_PAGES for symbol in normalized)
    ):
        raise ValueError("earnings symbols must be supported exactly once")
    return normalized


def refresh_earnings(
    symbols: Iterable[str],
    fetch: Callable[[str], str],
    now: datetime,
) -> dict:
    """Return confirmed future earnings dates for the requested symbols."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("retrieval timestamp must be timezone-aware")
    normalized = _validated_symbols(symbols)
    today = now.astimezone(NEW_YORK).date()
    dates = {}
    for symbol in normalized:
        earnings_date = _future_confirmed_date(fetch(symbol), symbol, today)
        dates[symbol] = earnings_date.isoformat()
        LOGGER.info("Confirmed earnings date for %s: %s", symbol, earnings_date)
    LOGGER.info("Earnings data retrieved at %s for %s", now.isoformat(), ",".join(normalized))
    return {
        "source": SOURCE,
        "retrieved_at": now.isoformat(),
        "symbols": dates,
    }


def write_earnings_cache(
    path: str | os.PathLike[str],
    symbols: Iterable[str],
    fetch: Callable[[str], str],
    now: datetime,
) -> None:
    """Atomically replace *path* with a fully refreshed earnings payload."""
    payload = refresh_earnings(symbols, fetch, now)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _configured_symbols() -> tuple[str, ...]:
    symbols = tuple(
        symbol.strip().upper() for symbol in str(DEFAULT_CONFIG.get("watchlist", "")).split(",")
    )
    if not all(symbols) or len(symbols) != 7 or len(set(symbols)) != 7:
        raise ValueError("watchlist must contain exactly 7 unique symbols")
    return symbols


def _refreshed_on_new_york_date(target: Path, local_date: date) -> bool:
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        retrieved_at = datetime.fromisoformat(payload["retrieved_at"])
        return (
            payload.get("source") == SOURCE
            and retrieved_at.tzinfo is not None
            and retrieved_at.utcoffset() is not None
            and retrieved_at.astimezone(NEW_YORK).date() == local_date
        )
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _scheduled_refresh_due(now: datetime, target: Path) -> bool:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("retrieval timestamp must be timezone-aware")
    local = now.astimezone(NEW_YORK)
    if local.weekday() >= 5 or (local.hour, local.minute) != (8, 30):
        return False
    return not _refreshed_on_new_york_date(target, local.date())


def main(
    *,
    fetch: Callable[[str], str] = fetch_page,
    now: datetime | None = None,
    scheduled: bool = False,
) -> None:
    """Refresh the env-backed earnings cache for the configured watchlist."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    retrieved_at = datetime.now(timezone.utc) if now is None else now
    target = Path(str(DEFAULT_CONFIG["options_earnings_path"]))
    if scheduled and not _scheduled_refresh_due(retrieved_at, target):
        return
    write_earnings_cache(target, _configured_symbols(), fetch, retrieved_at)
    print(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduled", action="store_true")
    main(scheduled=parser.parse_args().scheduled)
