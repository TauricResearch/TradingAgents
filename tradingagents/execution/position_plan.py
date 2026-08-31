"""Per-ticker position plans: time horizon and stop tracking."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dateutil.relativedelta import relativedelta

from .parser import extract_time_horizon

_MONTHS_RANGE_RE = re.compile(
    r"(\d+)\s*(?:-|to|–|—)\s*(\d+)\s*months?",
    re.IGNORECASE,
)
_MONTHS_SINGLE_RE = re.compile(r"(\d+)\s*months?", re.IGNORECASE)
_WEEKS_RE = re.compile(r"(\d+)\s*weeks?", re.IGNORECASE)
_YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*years?", re.IGNORECASE)


def extract_time_horizon_from_pm(text: str) -> str | None:
    """Read **Time Horizon** from PM markdown (alias for the parser helper)."""
    return extract_time_horizon(text)


def horizon_end_date(entry_date: str, horizon_text: str | None) -> str | None:
    """Return ISO end date using the longer bound of a range (e.g. 3-6 months -> 6 months)."""
    if not horizon_text or not entry_date:
        return None
    try:
        start = date.fromisoformat(str(entry_date)[:10])
    except ValueError:
        return None

    text = horizon_text.strip().lower()
    delta: relativedelta | None = None

    match = _MONTHS_RANGE_RE.search(text)
    if match:
        high = int(match.group(2))
        delta = relativedelta(months=high)
    else:
        match = _MONTHS_SINGLE_RE.search(text)
        if match:
            delta = relativedelta(months=int(match.group(1)))
        else:
            match = _WEEKS_RE.search(text)
            if match:
                delta = relativedelta(weeks=int(match.group(1)))
            else:
                match = _YEARS_RE.search(text)
                if match:
                    months = max(1, int(float(match.group(1)) * 12))
                    delta = relativedelta(months=months)

    if delta is None:
        return None
    return (start + delta).isoformat()


def load_position_plans(path: str) -> dict[str, Any]:
    plan_path = Path(path).expanduser()
    if not plan_path.exists():
        return {}
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_position_plans(path: str, plans: dict[str, Any]) -> None:
    plan_path = Path(path).expanduser()
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plans, indent=2), encoding="utf-8")


def plan_storage_key(*, account_scope: str | None, ticker: str) -> str:
    scope = (account_scope or "default").strip().lower()
    return f"{scope}:{ticker.upper()}"


def upsert_position_plan(
    plans: dict[str, Any],
    *,
    account_scope: str | None,
    ticker: str,
    trade_date: str,
    portfolio_manager_text: str,
    parsed_decision: dict[str, Any],
    limit_price: float | None,
    stop_loss: float | None,
    take_profit: float | None,
) -> dict[str, Any]:
    """Record or refresh the active plan when opening or adding to a position."""
    key = plan_storage_key(account_scope=account_scope, ticker=ticker)
    horizon_raw = extract_time_horizon(portfolio_manager_text) or parsed_decision.get(
        "time_horizon"
    )
    entry = str(trade_date)[:10]
    existing = plans.get(key) or {}
    if not existing.get("entry_date"):
        existing["entry_date"] = entry
    plans[key] = {
        **existing,
        "ticker": ticker.upper(),
        "entry_date": existing.get("entry_date") or entry,
        "time_horizon": horizon_raw,
        "horizon_end_date": horizon_end_date(
            existing.get("entry_date") or entry, horizon_raw
        ),
        "rating": parsed_decision.get("rating"),
        "stop_loss": stop_loss
        if stop_loss is not None
        else parsed_decision.get("stop_loss"),
        "take_profit": take_profit,
        "entry_limit": limit_price,
        "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return plans


def clear_position_plan(
    plans: dict[str, Any], *, account_scope: str | None, ticker: str
) -> dict[str, Any]:
    """Drop the stored plan after a full exit."""
    key = plan_storage_key(account_scope=account_scope, ticker=ticker)
    plans.pop(key, None)
    return plans


def _parse_iso_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def stop_loss_breached(
    *,
    current_price: float | None,
    stop_loss: float | None,
) -> bool:
    if current_price is None or stop_loss is None or stop_loss <= 0:
        return False
    return current_price < stop_loss


def horizon_elapsed(*, plan: dict[str, Any] | None, trade_date: str) -> bool:
    """True when the stored hold window is over (sell time)."""
    if not plan:
        return False
    end = _parse_iso_day(plan.get("horizon_end_date"))
    if end is None:
        return False
    today = _parse_iso_day(trade_date) or date.today()
    return today > end


def is_within_horizon(*, plan: dict[str, Any] | None, trade_date: str) -> bool:
    if not plan:
        return False
    end = _parse_iso_day(plan.get("horizon_end_date"))
    if end is None:
        return False
    today = _parse_iso_day(trade_date) or date.today()
    return today <= end


def plan_blocks_sell(
    *,
    plan: dict[str, Any] | None,
    trade_date: str,
    parsed_decision: dict[str, Any],
    current_price: float | None,
) -> tuple[bool, str]:
    """True when an existing position should stay on plan (no discretionary exit)."""
    stop = _to_float_optional(parsed_decision.get("stop_loss")) or _to_float_optional(
        (plan or {}).get("stop_loss")
    )
    if stop_loss_breached(current_price=current_price, stop_loss=stop):
        return False, "Stop-loss level breached; significant-loss exit allowed."

    if not plan:
        return False, ""

    if is_within_horizon(plan=plan, trade_date=trade_date):
        horizon = plan.get("time_horizon") or "thesis horizon"
        return (
            True,
            f"Within plan window ({horizon}); holding unless the stop is hit.",
        )

    if horizon_elapsed(plan=plan, trade_date=trade_date):
        return False, "Sell time: the estimated hold window has elapsed."

    return False, ""


def _to_float_optional(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
