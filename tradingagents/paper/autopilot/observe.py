"""Koral Equities: independent, observation-only NY market data pilot.

This module cannot create investment intents, modify any paper account or
call an AI model. It is intentionally limited to immutable source snapshots
and operator-visible collection diagnostics in a SEPARATE observation folder.

No exchange-certified data: Yahoo and Nasdaq are secondary sources. An
apparently successful fetch is not permission to execute a paper order.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from tradingagents.paper.autopilot import feeds
from tradingagents.paper.autopilot.observer_lock import observer_instance_lock
from tradingagents.paper.autopilot.state import normalize_tickers

DEFAULT_OBSERVATION_HOME = Path.home() / ".tradingagents" / "observations" / "koral_v3"


def observation_home(path: Path) -> Path:
    """Reject accidental selection of a portfolio or credential directory."""
    home = path.expanduser().resolve()
    paper = (Path.home() / ".tradingagents" / "paper").resolve()
    if home == paper or paper in home.parents:
        raise ValueError("Observation directory cannot be inside paper accounts")
    if any((home / name).exists() for name in ("portfolio.json", ".env")):
        raise ValueError("Observation directory contains an account or credentials")
    return home


def _utc(now: datetime) -> str:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Observation timestamp must be timezone aware")
    return now.astimezone(timezone.utc).isoformat()


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".koral-observe-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(data, output, sort_keys=True, indent=2, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active_phase(now: datetime) -> str | None:
    """Return exactly one NY capture window without backdating any source."""
    for phase in ("preopen", "preclose", "close"):
        try:
            feeds.session_cutoff(now, phase)
            return phase
        except ValueError:
            continue
    return None


def capture(
    directory: Path,
    symbols: list[str],
    *,
    now: datetime | None = None,
    earnings_source=None,
    prices_source=None,
    corporate_guard=None,
    completion_clock=None,
) -> dict:
    """Capture a single due phase; never read or write V1/V2/V3 paper files.

    Dependencies can be injected for offline tests. The CLI does not accept a
    caller-supplied observation date or time: a live observation uses real UTC.
    """
    current = now or datetime.now(timezone.utc)
    home = observation_home(directory)
    tickers = normalize_tickers(symbols)
    phase = active_phase(current)
    if phase is None:
        return {"status": "WAITING_FOR_NY_WINDOW", "mode": "OBSERVE_ONLY",
                "utc": _utc(current), "orders": 0}
    day = feeds.session_cutoff(current, phase)
    if phase in ("preopen", "preclose"):
        target = home / "calendar" / day / (phase + ".json")
    else:
        target = home / "market" / (day + ".json")
    if target.exists():
        # A saved phase never silently satisfies a DIFFERENT watchlist.
        if not target.is_file():
            raise ValueError("Observation target is not a regular file")
        prior = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(prior, dict) or prior.get("session") != day:
            raise ValueError("Invalid archived observation")
        if phase in ("preopen", "preclose"):
            expected = set(tickers)
            observed = prior.get("earnings")
            if (prior.get("phase") != phase or not isinstance(observed, dict)
                    or set(observed) != expected):
                raise ValueError("Archived earnings observation has a different symbol set")
        else:
            expected = set(tickers) | {"SPY"}
            observed = prior.get("ohlc_usd")
            if (prior.get("phase") != "close" or prior.get("mode") != "OBSERVE_ONLY"
                    or not isinstance(observed, dict) or set(observed) != expected):
                raise ValueError("Archived market observation has a different symbol set")
        return {"status": "ALREADY_CAPTURED", "mode": "OBSERVE_ONLY",
                "phase": phase, "session": day, "sha256": _sha(target),
                "orders": 0}
    if phase in ("preopen", "preclose"):
        source = earnings_source or feeds.earnings_for
        saved = feeds.capture_earnings(home, day, phase, tickers, current,
                                       source=source, completion_clock=completion_clock)
        record = json.loads(saved.read_text(encoding="utf-8"))
        observations = record["earnings"]
        verified = sorted(t for t, v in observations.items() if v.get("verified") is True)
        unverified = sorted(set(tickers) - set(verified))
        return {"status": "CAPTURED", "mode": "OBSERVE_ONLY",
                "phase": phase, "session": day, "sha256": _sha(saved),
                "verified": verified, "unverified": unverified,
                "orders": 0}
    load = prices_source or feeds.fetch_session_prices
    guard = corporate_guard or feeds.reject_unmodelled_corporate_actions
    quotes, fx_converter = load(set(tickers), day, day)
    needed = set(tickers) | {"SPY"}
    if not isinstance(quotes, dict):
        raise ValueError("Market-data feed returned an invalid response")
    missing = needed - set(quotes)
    if missing:
        raise ValueError(f"Missing mandatory source: {sorted(missing)}")
    bars = {}
    for ticker in sorted(needed):
        item = quotes[ticker].get(day)
        if item is None or not item.valid():
            raise ValueError(f"Missing or invalid complete {day} OHLC for {ticker}")
        bars[ticker] = asdict(item)
    if "GBPUSD=X" not in quotes:
        raise ValueError("Missing GBPUSD market data")
    gbp_open, gbp_close = fx_converter(quotes["GBPUSD=X"], day)
    if (type(gbp_open) not in (float, int) or type(gbp_close) not in (float, int)
            or not (0.3 <= gbp_open <= 2 and 0.3 <= gbp_close <= 2)):
        raise ValueError("Invalid GBP conversion from vendor")
    # Not a modelling shortcut: source actions must be independently provided.
    guard(set(tickers), day, day)
    finished = (completion_clock or (lambda: datetime.now(timezone.utc)))()
    if finished.tzinfo is None or finished.utcoffset() is None:
        raise ValueError("Market collection completion clock must be timezone aware")
    try:
        completed_session = feeds.session_cutoff(finished, "close")
    except ValueError as exc:
        raise ValueError("Market source fetch finished outside its completed NY session") from exc
    if (finished.astimezone(timezone.utc) < current.astimezone(timezone.utc) or
            completed_session != day):
        raise ValueError("Market source fetch finished outside its completed NY session")
    payload = {
        "schema": "koral-observation-v1", "mode": "OBSERVE_ONLY",
        "session": day, "phase": "close", "capture_started_utc": _utc(current),
        "capture_completed_utc": _utc(finished),
        "source": "YAHOO_SECONDARY_NOT_EXCHANGE_CERTIFIED",
        "ohlc_usd": bars, "fx_gbp_per_usd_open": gbp_open,
        "fx_gbp_per_usd_close": gbp_close,
        "corporate_actions": "QUERIED_NO_UNMODELLED_EVENTS_REPORTED",
        "notice": "Source observation, not a trade or an authorised paper fill.",
        "orders": [],
    }
    # Publish a completely written snapshot without replacing evidence.
    # os.link is an exclusive same-volume create on Windows NTFS and POSIX.
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=".market-observe-", suffix=".tmp", dir=target.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(payload, output, sort_keys=True, indent=2, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            raise ValueError("Concurrent observation already exists") from None
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"status": "CAPTURED", "mode": "OBSERVE_ONLY",
            "phase": phase, "session": day, "sha256": _sha(target),
            "symbols": sorted(needed), "orders": 0}


def monitor(
    directory: Path,
    symbols: list[str],
    *,
    poll_seconds: int = 60,
    once: bool = False,
) -> dict | None:
    """Poll NY source windows; no scheduler authority over trading accounts."""
    if type(poll_seconds) is not int or not 30 <= poll_seconds <= 3600:
        raise ValueError("Poll must be 30–3600 seconds")
    home = observation_home(directory)
    tickers = normalize_tickers(symbols)
    # The OS releases the lock even after an unclean process exit. Its
    # persistent file must never be deleted to "recover" an old observer.
    with observer_instance_lock(home):
        return _monitor_locked(home, tickers, poll_seconds=poll_seconds, once=once)


def _monitor_locked(home: Path, tickers: list[str], *,
                    poll_seconds: int, once: bool) -> dict | None:
    if once:
        return capture(home, tickers)
    print("KORAL OBSERVER ACTIVE: source snapshots only; NO PAPER OR REAL ORDERS.",
          flush=True)
    errors = home / "errors.jsonl"
    while True:
        now = datetime.now(timezone.utc)
        home.mkdir(parents=True, exist_ok=True)
        _atomic_json(home / "heartbeat.json", {
            "mode": "OBSERVE_ONLY", "utc": _utc(now),
            "tickers": tickers, "trading_enabled": False,
        })
        try:
            result = capture(home, tickers, now=now)
            if result["status"] != "WAITING_FOR_NY_WINDOW":
                print(json.dumps(result, sort_keys=True), flush=True)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            # Failure is logged in a separate diagnostic folder, never a book.
            with errors.open("a", encoding="utf-8") as output:
                output.write(json.dumps({
                    "utc": _utc(now), "phase": active_phase(now),
                    "error_type": type(exc).__name__, "mode": "OBSERVE_ONLY",
                    "message": str(exc)[:300],
                }, sort_keys=True) + "\n")
            print(f"OBSERVATION FAILED CLOSED: {type(exc).__name__}: {exc}",
                  flush=True)
        time.sleep(poll_seconds)
