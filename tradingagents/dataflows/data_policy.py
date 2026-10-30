"""What a run does when the data it needs is missing, checked before any model call.

The router answers a call no vendor could serve with a sentinel
(``NO_DATA_AVAILABLE`` or ``DATA_UNAVAILABLE``) so the run survives vendor
errors, and the analysts report the gap. A run can instead be told that some
data is required: ``data_policy`` maps a kind of data to a level, and the check
asks the router for each kind once, with the run's ticker and date, before the
graph starts. A mistyped or delisted ticker then stops in seconds instead of
running every agent on nothing.

    data_policy = {"prices": "abort", "news": "warn"}

Left empty, the default, nothing is checked and a run behaves as before.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.router import route_to_vendor

logger = logging.getLogger(__name__)

LEVELS = ("off", "warn", "abort")

# Each kind is asked for with one call, as an analyst would ask for it: the
# method and its arguments for a ticker and a trade date.
_PROBES = {
    "prices": lambda ticker, date: ("get_stock_data", ticker, _days_before(date, 30), date),
    "fundamentals": lambda ticker, date: ("get_fundamentals", ticker, date),
    "news": lambda ticker, date: ("get_news", ticker, _days_before(date, 7), date),
    "macro": lambda ticker, date: ("get_macro_indicators", "fed_funds_rate", date, None),
}
KINDS = tuple(_PROBES)

# What the router returns, in place of data, when no vendor could serve a call.
_SENTINELS = ("NO_DATA_AVAILABLE", "DATA_UNAVAILABLE")


class DataPolicyError(RuntimeError):
    """The data a run was told it requires could not be retrieved."""

    def __init__(self, ticker: str, trade_date: str, missing: list[MissingData]):
        self.ticker, self.trade_date, self.missing = ticker, trade_date, missing
        lines = "\n".join(f"  {gap}" for gap in missing)
        super().__init__(f"Required data is missing for {ticker} on {trade_date}; "
                         f"the run stopped before any model call:\n{lines}")


@dataclass(frozen=True)
class MissingData:
    kind: str
    level: str
    reason: str

    def __str__(self) -> str:
        return f"{self.kind}: {self.reason}"


def _days_before(date: str, days: int) -> str:
    return (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")


def parse_data_policy(value: str | Mapping[str, str] | None) -> dict[str, str]:
    """A policy as ``{kind: level}``, from a mapping or from ``"prices=abort,news=warn"``.

    An unknown kind or level raises ``ValueError``: a misspelled policy must not
    quietly check nothing.
    """
    if not value:
        return {}
    if isinstance(value, str):
        pairs = {}
        for item in (part.strip() for part in value.split(",")):
            if not item:
                continue
            kind, sep, level = item.partition("=")
            if not sep:
                raise ValueError(f"data policy entry {item!r} is not kind=level, e.g. prices=abort")
            pairs[kind.strip()] = level.strip()
        value = pairs
    policy = {}
    for kind, level in value.items():
        kind, level = str(kind).strip().lower(), str(level).strip().lower()
        if kind not in _PROBES:
            raise ValueError(f"unknown data kind {kind!r} in data policy; choose from {', '.join(KINDS)}")
        if level not in LEVELS:
            raise ValueError(f"unknown level {level!r} for {kind} in data policy; choose from {', '.join(LEVELS)}")
        policy[kind] = level
    return policy


def _missing_reason(kind: str, ticker: str, trade_date: str) -> str | None:
    """Why ``kind`` could not be retrieved, or None when the router served it."""
    method, *args = _PROBES[kind](ticker, trade_date)
    try:
        answer = route_to_vendor(method, *args)
    except Exception as exc:  # a core category raises when its only vendor failed
        return f"{type(exc).__name__}: {exc}"
    text = str(answer).lstrip()
    if not text.startswith(_SENTINELS):
        return None
    # The sentinel states the cause, in parentheses, then instructs the model;
    # only the cause is kept. The cause can itself hold sentences.
    end = text.find(").")
    return text[:end + 1] if end != -1 else text.split(". ", 1)[0]


def check_data_policy(config: Mapping, ticker: str, trade_date: str) -> list[MissingData]:
    """Ask the router for each kind the policy names, under ``config``'s vendors.

    Returns what is missing at ``warn``, each also logged. Raises
    ``DataPolicyError`` when anything is missing at ``abort``. Kinds at ``off``,
    and every kind when ``config`` has no ``data_policy``, are not asked for.
    """
    policy = {kind: level for kind, level in parse_data_policy(config.get("data_policy")).items()
              if level != "off"}
    if not policy:
        return []
    missing = []
    with run_config(dict(config)):
        for kind, level in policy.items():
            reason = _missing_reason(kind, ticker, trade_date)
            if reason is not None:
                missing.append(MissingData(kind, level, reason))
    for gap in missing:
        if gap.level == "warn":
            logger.warning("Data policy: %s is missing for %s on %s: %s", gap.kind, ticker, trade_date, gap.reason)
    if any(gap.level == "abort" for gap in missing):
        raise DataPolicyError(ticker, trade_date, missing)
    return missing
