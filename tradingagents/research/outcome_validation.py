"""Pure validation for the frozen exploratory outcome adapter."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from datetime import date
from typing import Any

from tradingagents.domain.contracts import canonical_json
from tradingagents.research.contracts import OutcomeObservation
from tradingagents.research.timeline import (
    decision_cutoff,
    outcome_capture_not_before,
    outcome_sessions,
)
from tradingagents.research_protocol import GLOBAL_EVENT_V2_PROTOCOL

_POLICY = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["price_capture"][
    "exploratory_history_adapter"
]


def _endpoint_rows(value: Any, expected_dates: tuple[date, date]) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("outcome provenance requires exactly two endpoint rows")
    prices = []
    for row, expected_date in zip(value, expected_dates, strict=True):
        if not isinstance(row, dict) or set(row) != {"date", "adjusted_open"}:
            raise ValueError("outcome endpoint provenance is malformed")
        if row["date"] != expected_date.isoformat():
            raise ValueError("outcome endpoint dates differ from the frozen horizon")
        price = row["adjusted_open"]
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise ValueError("outcome endpoint prices must be numeric")
        price = float(price)
        if not math.isfinite(price) or price <= 0.0:
            raise ValueError("outcome endpoint prices must be finite and positive")
        prices.append(price)
    return prices[0], prices[1]


def _same_return(actual: float | None, expected: float | None) -> bool:
    if actual is None or expected is None:
        return actual is expected
    return math.isclose(float(actual), expected, rel_tol=1e-12, abs_tol=1e-15)


def validate_outcome_observation(
    observation: OutcomeObservation,
    *,
    decision_date: date,
    universe: Sequence[str],
    benchmark: str,
    error_type: str | None = None,
) -> None:
    """Replay provider provenance instead of trusting stated return values."""
    provider = str(_POLICY["provider_id"])
    if observation.provider != provider:
        raise ValueError("outcome provider differs from the frozen protocol")
    if set(observation.asset_returns) != set(universe):
        raise ValueError("outcome provider returned a different universe")
    if observation.observed_at <= decision_cutoff(decision_date):
        raise ValueError("outcome was captured before its decision cutoff")
    delay = int(
        GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["price_capture"]
        ["scheduled_delay_after_xnys_session_open_minutes"]
    )
    if observation.observed_at < outcome_capture_not_before(
        decision_date, delay_minutes=delay
    ):
        raise ValueError("outcome was captured before its scheduled mark")
    if observation.cash_return != float(_POLICY["cash_return"]):
        raise ValueError("outcome cash return differs from the frozen adapter policy")

    if error_type is not None:
        if error_type != "OutcomeUnavailableError":
            raise ValueError("unavailable outcome has a non-canonical error type")
        expected_hash = hashlib.sha256(
            f"{provider}:{decision_date.isoformat()}".encode()
        ).hexdigest()
        if (
            observation.entry_date is not None
            or observation.exit_date is not None
            or observation.benchmark_return is not None
            or any(value is not None for value in observation.asset_returns.values())
            or observation.raw_payload_sha256 != expected_hash
            or observation.vintage_id != f"unavailable:{decision_date.isoformat()}"
            or observation.provenance
            != {"provider": provider, "status": "provider_failure"}
        ):
            raise ValueError("unavailable outcome record is not canonical")
        return

    provenance = observation.provenance
    if not isinstance(provenance, dict) or set(provenance) != {
        "schema_version",
        "provider",
        "price_semantics",
        "endpoints",
    }:
        raise ValueError("outcome provenance does not match the frozen adapter schema")
    if (
        type(provenance["schema_version"]) is not int
        or provenance["schema_version"] != _POLICY["provenance_schema_version"]
        or provenance["provider"] != provider
        or provenance["price_semantics"] != _POLICY["price_semantics"]
    ):
        raise ValueError("outcome provenance differs from the frozen adapter policy")
    endpoints = provenance["endpoints"]
    expected_symbols = {*universe, benchmark}
    if not isinstance(endpoints, dict) or set(endpoints) != expected_symbols:
        raise ValueError("outcome provenance returned a different universe")

    horizon = outcome_sessions(decision_date)
    parsed = {symbol: _endpoint_rows(endpoints[symbol], horizon) for symbol in expected_symbols}
    benchmark_prices = parsed[benchmark]
    if benchmark_prices is None:
        expected_entry = expected_exit = None
        expected_benchmark_return = None
    else:
        expected_entry, expected_exit = horizon
        expected_benchmark_return = benchmark_prices[1] / benchmark_prices[0] - 1.0
    if (
        observation.entry_date != expected_entry
        or observation.exit_date != expected_exit
        or not _same_return(observation.benchmark_return, expected_benchmark_return)
    ):
        raise ValueError("outcome benchmark does not replay from its provenance")
    for symbol in universe:
        prices = parsed[symbol]
        expected = (
            prices[1] / prices[0] - 1.0
            if prices is not None and benchmark_prices is not None
            else None
        )
        if not _same_return(observation.asset_returns[symbol], expected):
            raise ValueError("outcome asset return does not replay from its provenance")
    if expected_exit is not None and observation.observed_at.date() < expected_exit:
        raise ValueError("outcome was captured before its exit session")

    raw_hash = hashlib.sha256(canonical_json(endpoints).encode()).hexdigest()
    expected_vintage = f"yfinance:{observation.observed_at.isoformat()}:{raw_hash[:16]}"
    if (
        observation.raw_payload_sha256 != raw_hash
        or observation.vintage_id != expected_vintage
    ):
        raise ValueError("outcome content identity does not replay from its provenance")
