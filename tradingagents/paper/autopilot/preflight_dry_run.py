"""Read-only readiness preflight for an observed, same-session AI dry run.

No model/vendor calls, no output files, no account reads or writes. Archived
Yahoo/Nasdaq source agreement is NOT exchange/issuer certification.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from tradingagents.paper.autopilot import live_dry_run, observe
from tradingagents.paper.autopilot.state import normalize_tickers

NY = ZoneInfo("America/New_York")


def inspect(observer: Path, session: str, tickers: list[str], *,
            now: datetime | None = None) -> dict:
    """Report whether a CURRENT, archived research candidate exists, no changes."""
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Readiness clock must be timezone-aware")
    names = normalize_tickers(tickers, cap=3)
    source = live_dry_run.read_observation(
        observer, session, names, current.astimezone(timezone.utc),
    )
    ny_now = current.astimezone(NY)
    same_session = (ny_now.date().isoformat() == session and
                    ny_now.time() >= time(17, 40))
    eligible = [ticker for ticker in names
                if source["tickers"][ticker]["eligible_for_research"]]
    can_request = bool(same_session and eligible)
    if can_request:
        status = "READ_ONLY_PREFLIGHT_AI_CANDIDATE_AVAILABLE"
    elif same_session:
        status = "READ_ONLY_PREFLIGHT_NO_ELIGIBLE_AI"
    else:
        status = "READ_ONLY_PREFLIGHT_HISTORICAL_AI_FORBIDDEN"
    return {
        "status": status,
        "session": session,
        "watchlist": names,
        "market_sha256": source["market_sha256"],
        "calendar_sha256": source["calendar_sha256"],
        "completed_capture_utc": source["capture_completed_utc"],
        "ai_eligible_tickers": eligible,
        "can_request_one_real_ai_now": can_request,
        "reasons": {ticker: source["tickers"][ticker]["reason"] for ticker in names},
        "account_reads": 0,
        "account_writes": 0,
        "broker_connected": False,
        "warning": "Secondary vendor data only; this check does not authorise orders or certify accuracy",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="koral-equities-preflight",
        description="Inspect archived market/earnings evidence without AI, trades, or output writes",
    )
    parser.add_argument("--observer", type=Path, default=observe.DEFAULT_OBSERVATION_HOME)
    parser.add_argument("--session", required=True)
    parser.add_argument("--tickers", nargs="+", required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect(args.observer, args.session, args.tickers)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"RESEARCH PREFLIGHT BLOCKED: {type(exc).__name__}: {exc}")
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
