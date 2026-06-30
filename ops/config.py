"""Operational config for the live-trading layer.

Defaults match docs/superpowers/specs/2026-06-30-tradingagents-live-v1-design.md
section "Guardrail rules". Override at runtime via OPS_* env vars.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

_DEFAULT_DENY_LIST = frozenset({
    "SPOT",
    "TQQQ", "SQQQ", "UPRO", "SPXU", "UVXY", "SVXY",
    "SOXL", "SOXS", "LABU", "LABD", "TNA", "TZA",
    "TMF", "TMV", "QLD", "QID",
})


@dataclass(frozen=True)
class OpsConfig:
    broker_mode: str = "paper"  # "paper" or "robinhood"
    deny_list: frozenset[str] = field(default_factory=lambda: _DEFAULT_DENY_LIST)  # Not env-overridable; extend via code
    per_position_cap_pct: Decimal = Decimal("0.10")
    per_trade_dollar_floor: Decimal = Decimal("5")
    max_open_positions: int = 5
    cash_reserve_pct: Decimal = Decimal("0.20")
    daily_drawdown_pct: Decimal = Decimal("-0.07")
    weekly_drawdown_pct: Decimal = Decimal("-0.15")
    per_position_stop_pct: Decimal = Decimal("-0.08")
    journal_path: str = "ops_journal.sqlite"


def _env_decimal(name: str) -> Decimal | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid value for {name!r}: {raw!r}") from exc


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid value for {name!r}: {raw!r}") from exc


def load_config() -> OpsConfig:
    kwargs: dict = {}

    broker_mode = os.environ.get("OPS_BROKER_MODE")
    if broker_mode is not None:
        kwargs["broker_mode"] = broker_mode

    per_position_cap_pct = _env_decimal("OPS_PER_POSITION_CAP_PCT")
    if per_position_cap_pct is not None:
        kwargs["per_position_cap_pct"] = per_position_cap_pct

    per_trade_dollar_floor = _env_decimal("OPS_PER_TRADE_DOLLAR_FLOOR")
    if per_trade_dollar_floor is not None:
        kwargs["per_trade_dollar_floor"] = per_trade_dollar_floor

    max_open_positions = _env_int("OPS_MAX_OPEN_POSITIONS")
    if max_open_positions is not None:
        kwargs["max_open_positions"] = max_open_positions

    cash_reserve_pct = _env_decimal("OPS_CASH_RESERVE_PCT")
    if cash_reserve_pct is not None:
        kwargs["cash_reserve_pct"] = cash_reserve_pct

    daily_drawdown_pct = _env_decimal("OPS_DAILY_DRAWDOWN_PCT")
    if daily_drawdown_pct is not None:
        kwargs["daily_drawdown_pct"] = daily_drawdown_pct

    weekly_drawdown_pct = _env_decimal("OPS_WEEKLY_DRAWDOWN_PCT")
    if weekly_drawdown_pct is not None:
        kwargs["weekly_drawdown_pct"] = weekly_drawdown_pct

    per_position_stop_pct = _env_decimal("OPS_PER_POSITION_STOP_PCT")
    if per_position_stop_pct is not None:
        kwargs["per_position_stop_pct"] = per_position_stop_pct

    journal_path = os.environ.get("OPS_JOURNAL_PATH")
    if journal_path is not None:
        kwargs["journal_path"] = journal_path

    return OpsConfig(**kwargs)
