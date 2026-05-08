"""Daily rate limit for propagate_market calls.

Backstop against runaway loops, accidental --limit 9999 flags, or any
scenario where the bot would otherwise rack up unbounded LLM spend.

Counts the number of propagate_market invocations per UTC day and
short-circuits to a synthetic HOLD once the cap is hit. The count is
persisted to disk so it survives across CLI invocations within the
same UTC day (a single launchd run or several manual runs all share
the same budget).

Default cap: 100 calls/day. Override with POLYMARKET_DAILY_CALL_LIMIT
env var. Setting the env var to 0 disables the limit entirely.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from tradingagents.exchange.io_utils import POLYMARKET_OUTPUT_DIR

logger = logging.getLogger(__name__)

DEFAULT_DAILY_LIMIT = 100
ENV_DAILY_LIMIT = "POLYMARKET_DAILY_CALL_LIMIT"
STATE_FILE = POLYMARKET_OUTPUT_DIR / "rate_limit.json"


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {"day": _utc_today(), "count": 0}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state, dict) or "day" not in state or "count" not in state:
            return {"day": _utc_today(), "count": 0}
        return state
    except (json.JSONDecodeError, OSError):
        return {"day": _utc_today(), "count": 0}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(state, f)


def _resolve_limit() -> int:
    """Return the configured daily limit. 0 means 'disabled'."""
    raw = os.environ.get(ENV_DAILY_LIMIT)
    if raw is None:
        return DEFAULT_DAILY_LIMIT
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid %s=%r; using default %d",
            ENV_DAILY_LIMIT,
            raw,
            DEFAULT_DAILY_LIMIT,
        )
        return DEFAULT_DAILY_LIMIT


def is_exceeded() -> bool:
    """True if today's call count is at or above the configured cap.

    Also rolls over the count when the UTC date changes.
    """
    limit = _resolve_limit()
    if limit <= 0:
        return False
    state = _load_state()
    if state["day"] != _utc_today():
        return False
    return state["count"] >= limit


def record_call() -> int:
    """Increment today's call count. Resets if the UTC date rolled over.

    Returns the post-increment count.
    """
    today = _utc_today()
    state = _load_state()
    if state["day"] != today:
        state = {"day": today, "count": 0}
    state["count"] += 1
    _save_state(state)
    return state["count"]


def get_status() -> dict:
    """Snapshot of today's count and configured limit. For diagnostics."""
    state = _load_state()
    today = _utc_today()
    return {
        "day": state["day"],
        "count": state["count"] if state["day"] == today else 0,
        "limit": _resolve_limit(),
        "exceeded": is_exceeded(),
    }
