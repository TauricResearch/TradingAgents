"""Operational config for the live-trading layer.

Defaults match docs/superpowers/specs/2026-06-30-tradingagents-live-v1-design.md
section "Guardrail rules". Override at runtime via OPS_* env vars.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal

_DEFAULT_DENY_LIST = frozenset({
    "SPOT",
    "TQQQ", "SQQQ", "UPRO", "SPXU", "UVXY", "SVXY",
    "SOXL", "SOXS", "LABU", "LABD", "TNA", "TZA",
    "TMF", "TMV", "QLD", "QID",
})


@dataclass(frozen=True)
class OpsConfig:
    broker_mode: str = "paper"  # "paper" or "robinhood"
    deny_list: frozenset[str] = field(default_factory=lambda: _DEFAULT_DENY_LIST)
    per_position_cap_pct: Decimal = Decimal("0.10")
    per_trade_dollar_floor: Decimal = Decimal("5")
    max_open_positions: int = 5
    cash_reserve_pct: Decimal = Decimal("0.20")
    daily_drawdown_pct: Decimal = Decimal("-0.07")
    weekly_drawdown_pct: Decimal = Decimal("-0.15")
    per_position_stop_pct: Decimal = Decimal("-0.08")
    journal_path: str = "ops_journal.sqlite"


def _env_decimal(name: str, default: Decimal) -> Decimal:
    raw = os.environ.get(name)
    return Decimal(raw) if raw is not None else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw is not None else default


def load_config() -> OpsConfig:
    return OpsConfig(
        broker_mode=os.environ.get("OPS_BROKER_MODE", "paper"),
        per_position_cap_pct=_env_decimal("OPS_PER_POSITION_CAP_PCT", Decimal("0.10")),
        per_trade_dollar_floor=_env_decimal("OPS_PER_TRADE_DOLLAR_FLOOR", Decimal("5")),
        max_open_positions=_env_int("OPS_MAX_OPEN_POSITIONS", 5),
        cash_reserve_pct=_env_decimal("OPS_CASH_RESERVE_PCT", Decimal("0.20")),
        daily_drawdown_pct=_env_decimal("OPS_DAILY_DRAWDOWN_PCT", Decimal("-0.07")),
        weekly_drawdown_pct=_env_decimal("OPS_WEEKLY_DRAWDOWN_PCT", Decimal("-0.15")),
        per_position_stop_pct=_env_decimal("OPS_PER_POSITION_STOP_PCT", Decimal("-0.08")),
        journal_path=os.environ.get("OPS_JOURNAL_PATH", "ops_journal.sqlite"),
    )
