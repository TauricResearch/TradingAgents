"""Immutable run identity and portfolio snapshot canonicalization."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tradingagents.portfolio import PortfolioContext


class InputMode(StrEnum):
    NO_PORTFOLIO = "NO_PORTFOLIO"
    PORTFOLIO_PROVIDED = "PORTFOLIO_PROVIDED"


class ConsentState(StrEnum):
    FROZEN = "FROZEN"
    CONFIRMED = "CONFIRMED"


@dataclass(frozen=True)
class FrozenSnapshot:
    basename: str
    cash: float | None
    currency: str | None
    positions: tuple[tuple[str, float, float | None], ...]
    fingerprint_sha256: str
    portfolio_as_of: str
    as_of_basis: str = "USER_CONFIRMED"

    def __post_init__(self):
        if not re.fullmatch(r"[0-9a-f]{64}", self.fingerprint_sha256):
            raise ValueError("snapshot fingerprint must be a full SHA-256 digest")
        object.__setattr__(self, "positions", tuple(tuple(row) for row in self.positions))

    def portfolio_context(self) -> PortfolioContext:
        from tradingagents.portfolio import PortfolioContext
        return PortfolioContext.model_validate({
            "cash": self.cash, "currency": self.currency,
            "positions": [
                {"ticker": ticker, "quantity": quantity, "average_price": average_price}
                for ticker, quantity, average_price in self.positions
            ],
        })


def _number(value: float | int | None):
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("portfolio numbers must be finite")
    if number == 0:
        number = 0.0
    if number.is_integer() and abs(number) < 2**53:
        return int(number)
    return number


def canonical_portfolio(portfolio: PortfolioContext) -> tuple[dict, tuple[tuple[str, float, float | None], ...]]:
    rows = []
    for position in portfolio.positions:
        ticker = position.ticker.strip().upper()
        if not ticker:
            raise ValueError("portfolio ticker cannot be empty")
        quantity = float(position.quantity)
        average_price = None if position.average_price is None else float(position.average_price)
        row = {"ticker": ticker, "quantity": _number(quantity),
               "average_price": _number(average_price)}
        price_key = (0, 0.0) if average_price is None else (1, average_price)
        rows.append((ticker, quantity, average_price, row, price_key))
    rows.sort(key=lambda item: (item[0], item[1], item[4]))
    normalized = {
        "cash": _number(portfolio.cash),
        "currency": portfolio.currency,
        "positions": [item[3] for item in rows],
    }
    frozen_rows = tuple((ticker, quantity, price) for ticker, quantity, price, _, _ in rows)
    return normalized, frozen_rows


def snapshot_fingerprint(portfolio: PortfolioContext) -> tuple[str, tuple[tuple[str, float, float | None], ...]]:
    normalized, rows = canonical_portfolio(portfolio)
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), rows


@dataclass(frozen=True)
class RunContext:
    run_id: str
    ticker: str
    analysis_date: str
    mode: InputMode
    snapshot: FrozenSnapshot | None
    unverified_holdings: bool
    provider_transmission_disclosed: bool
    consent_state: ConsentState = ConsentState.FROZEN

    def __post_init__(self):
        if (self.mode == InputMode.NO_PORTFOLIO) != (self.snapshot is None):
            raise ValueError("snapshot must be absent exactly in NO_PORTFOLIO mode")
        if not self.run_id or not self.ticker.strip():
            raise ValueError("run_id and ticker are required")

    def confirm(self) -> RunContext:
        if self.consent_state != ConsentState.FROZEN:
            raise ValueError("only a frozen run context can be confirmed")
        return RunContext(
            self.run_id, self.ticker, self.analysis_date, self.mode, self.snapshot,
            self.unverified_holdings, self.provider_transmission_disclosed,
            ConsentState.CONFIRMED,
        )

    def portfolio_context(self) -> PortfolioContext | None:
        return self.snapshot.portfolio_context() if self.snapshot else None

    def safe_input_metadata(self) -> dict:
        snapshot = self.snapshot
        return {
            "run_id": self.run_id, "ticker": self.ticker,
            "analysis_date": self.analysis_date, "input_mode": self.mode.value,
            "basename": snapshot.basename if snapshot else None,
            "fingerprint_sha256": snapshot.fingerprint_sha256 if snapshot else None,
            "portfolio_as_of": snapshot.portfolio_as_of if snapshot else None,
            "as_of_basis": snapshot.as_of_basis if snapshot else None,
        }


def new_run_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"
