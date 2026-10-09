"""Deterministic pre-trade gate for explicitly typed PAPER intents.

The TradingAgents five-tier rating and the Trader's Buy/Sell/Hold proposal are
not orders. Callers must construct a TradeIntent deliberately and supply
independently sourced, timestamped market and portfolio snapshots.

This validates *proposed* quantities and price levels; it does not model fills,
exchange permissions, liquidation, funding, slippage or stop execution.
No external API, LLM or exchange is invoked by this module.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ACTION = Literal["HOLD", "SPOT_BUY", "SPOT_SELL", "SHORT_OPEN", "SHORT_CLOSE"]
_MARKET = Literal["SPOT", "PERPETUAL"]
_ORDER = Literal["MARKET", "LIMIT"]
_SYMBOL = re.compile(r"^[A-Z0-9]+[-/][A-Z0-9]+$")


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class TradeIntent(_ImmutableModel):
    """Explicit *simulation* instruction; ambiguous SELL is deliberately invalid."""

    symbol: str
    market: _MARKET
    action: _ACTION
    execution_mode: Literal["PAPER"] = "PAPER"
    order_type: _ORDER | None = None
    quantity_base: Decimal | None = Field(default=None, gt=0)
    limit_price: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)
    leverage: Decimal = Field(default=Decimal("1"), ge=1)
    idempotency_key: str | None = None

    @field_validator("symbol")
    @classmethod
    def _valid_symbol(cls, value: str) -> str:
        if not _SYMBOL.fullmatch(value):
            raise ValueError("symbol must be an explicit uppercase quote pair, e.g. BTC-USD")
        return value


class MarketSnapshot(_ImmutableModel):
    symbol: str
    price: Decimal = Field(gt=0)
    observed_at: datetime
    source: str = Field(min_length=2)

    @field_validator("observed_at")
    @classmethod
    def _aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("market timestamp must include a timezone")
        return value


class PortfolioSnapshot(_ImmutableModel):
    equity_quote: Decimal = Field(ge=0)
    free_quote: Decimal = Field(ge=0)
    free_base: Decimal = Field(ge=0)


class RiskLimits(_ImmutableModel):
    max_notional_fraction: Decimal = Field(default=Decimal("0.05"), gt=0, le=1)
    max_loss_fraction: Decimal = Field(default=Decimal("0.01"), gt=0, le=1)
    max_quote_age_seconds: int = Field(default=90, gt=0)


class TradeVerdict(_ImmutableModel):
    approved: bool
    reasons: tuple[str, ...]
    notional_quote: Decimal | None = None
    theoretical_stop_loss_quote: Decimal | None = None


def validate_intent(
    intent: TradeIntent,
    market: MarketSnapshot,
    portfolio: PortfolioSnapshot,
    *,
    now: datetime,
    limits: RiskLimits | None = None,
) -> TradeVerdict:
    """Validate one proposed paper order; fail closed on missing or contradictory data.

    Uses quote-currency accounting with no leverage, and assumes a hypothetical
    fill at the limit or snapshot price. It does not submit or reserve an order.
    Duplicate idempotency keys must later be rejected by the paper order store.
    """
    limits = limits or RiskLimits()
    errors: list[str] = []

    if intent.action == "HOLD":
        return TradeVerdict(approved=False, reasons=("HOLD_NO_ORDER",))
    if intent.action == "SHORT_CLOSE":
        errors.append("SHORT_CLOSE_NOT_IMPLEMENTED")
    if intent.action.startswith("SPOT_") and intent.market != "SPOT":
        errors.append("SPOT_ACTION_REQUIRES_SPOT_MARKET")
    if intent.action.startswith("SHORT_") and intent.market != "PERPETUAL":
        errors.append("SHORT_ACTION_REQUIRES_PERPETUAL_MARKET")
    if intent.leverage != 1:
        errors.append("LEVERAGE_NOT_SUPPORTED")
    if not intent.idempotency_key or not intent.idempotency_key.strip():
        errors.append("IDEMPOTENCY_KEY_REQUIRED")
    if intent.quantity_base is None:
        errors.append("QUANTITY_REQUIRED")
    if intent.order_type is None:
        errors.append("ORDER_TYPE_REQUIRED")
    if intent.order_type == "LIMIT" and intent.limit_price is None:
        errors.append("LIMIT_PRICE_REQUIRED")
    if intent.order_type == "MARKET" and intent.limit_price is not None:
        errors.append("MARKET_ORDER_MUST_NOT_HAVE_LIMIT_PRICE")
    if market.symbol != intent.symbol:
        errors.append("SYMBOL_MISMATCH")

    if now.tzinfo is None or now.utcoffset() is None:
        errors.append("VALIDATION_TIME_MUST_BE_TIMEZONE_AWARE")
    else:
        age = now - market.observed_at
        if age < -timedelta(seconds=5):
            errors.append("MARKET_SNAPSHOT_FROM_FUTURE")
        elif age > timedelta(seconds=limits.max_quote_age_seconds):
            errors.append("MARKET_SNAPSHOT_STALE")

    entry = intent.limit_price if intent.order_type == "LIMIT" else market.price
    if entry is None or intent.quantity_base is None:
        return TradeVerdict(approved=False, reasons=tuple(errors))
    notional = entry * intent.quantity_base
    loss_at_stop: Decimal | None = None

    if intent.action in ("SPOT_BUY", "SHORT_OPEN"):
        if portfolio.equity_quote <= 0:
            errors.append("PORTFOLIO_EQUITY_REQUIRED")
        elif notional > portfolio.equity_quote * limits.max_notional_fraction:
            errors.append("NOTIONAL_LIMIT_EXCEEDED")

        # Short positions require collateral even for this unleveraged simulation.
        if notional > portfolio.free_quote:
            errors.append("QUOTE_BALANCE_INSUFFICIENT")

        if intent.stop_loss is None:
            errors.append("STOP_LOSS_REQUIRED")
        if intent.take_profit is None:
            errors.append("TAKE_PROFIT_REQUIRED")
        if intent.stop_loss is not None and intent.take_profit is not None:
            if intent.action == "SPOT_BUY":
                if intent.stop_loss >= entry or intent.take_profit <= entry:
                    errors.append("LONG_PRICE_LEVELS_INVALID")
                else:
                    loss_at_stop = (entry - intent.stop_loss) * intent.quantity_base
            elif intent.action == "SHORT_OPEN":
                if intent.stop_loss <= entry or intent.take_profit >= entry:
                    errors.append("SHORT_PRICE_LEVELS_INVALID")
                else:
                    loss_at_stop = (intent.stop_loss - entry) * intent.quantity_base

        if (
            loss_at_stop is not None
            and loss_at_stop > portfolio.equity_quote * limits.max_loss_fraction
        ):
            errors.append("LOSS_BUDGET_EXCEEDED")
    elif intent.action == "SPOT_SELL":
        if intent.quantity_base > portfolio.free_base:
            errors.append("BASE_BALANCE_INSUFFICIENT")

    return TradeVerdict(
        approved=not errors,
        reasons=tuple(errors),
        notional_quote=notional,
        theoretical_stop_loss_quote=loss_at_stop,
    )
