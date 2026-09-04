"""Broker-independent policy primitives for a conservative options wheel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
CONTRACT_MULTIPLIER = Decimal("100")
MAX_QUOTE_AGE = timedelta(seconds=300)


@dataclass(frozen=True)
class OptionContract:
    symbol: str
    underlying: str
    kind: str
    strike: Decimal
    expiration: date
    delta: Decimal
    bid: Decimal
    ask: Decimal
    open_interest: Decimal
    quote_time: datetime


@dataclass(frozen=True)
class EquityPosition:
    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    current_price: Decimal


@dataclass(frozen=True)
class OptionPosition:
    symbol: str
    underlying: str
    kind: str
    qty: Decimal
    avg_entry_price: Decimal
    delta: Decimal


@dataclass(frozen=True)
class OptionOpenOrder:
    symbol: str
    underlying: str
    kind: str
    position_intent: str
    qty: Decimal
    filled_qty: Decimal
    strike: Decimal
    order_id: str = ""
    client_order_id: str = ""
    submitted_at: datetime | None = None


@dataclass(frozen=True)
class WheelReservations:
    put_collateral: dict[str, Decimal]
    covered_shares: dict[str, Decimal]


@dataclass(frozen=True)
class OptionIntent:
    symbol: str
    underlying: str
    kind: str
    side: str
    position_intent: str
    qty: Decimal
    limit_price: Decimal
    delta: Decimal


def contract_metrics(contract: OptionContract, now: datetime) -> tuple[Decimal, Decimal, int]:
    dte = (contract.expiration - now.astimezone(NEW_YORK).date()).days
    annualized_yield = contract.bid / contract.strike * Decimal(365) / Decimal(dte + 1)
    score = (
        (Decimal(1) - abs(contract.delta))
        * Decimal(250)
        / Decimal(dte + 5)
        * contract.bid
        / contract.strike
    )
    return annualized_yield, score, dte


def _valid_quote(contract: OptionContract, now: datetime) -> bool:
    if contract.quote_time is None or now.tzinfo is None or contract.quote_time.tzinfo is None:
        return False
    if not contract.bid.is_finite() or not contract.ask.is_finite():
        return False
    try:
        age = now - contract.quote_time
    except TypeError:
        return False
    return (
        timedelta(0) <= age <= MAX_QUOTE_AGE
        and contract.bid > 0
        and contract.ask > 0
        and contract.bid <= contract.ask
    )


def select_contract(
    contracts: tuple[OptionContract, ...],
    now: datetime,
    earnings_date: date | None,
) -> OptionContract | None:
    if earnings_date is not None:
        days_to_earnings = (earnings_date - now.astimezone(NEW_YORK).date()).days
        if 0 <= days_to_earnings <= 7:
            return None

    eligible: list[tuple[Decimal, str, OptionContract]] = []
    for contract in contracts:
        if not _valid_quote(contract, now) or contract.strike <= 0:
            continue
        try:
            annualized_yield, score, dte = contract_metrics(contract, now)
        except (ArithmeticError, InvalidOperation, ValueError):
            continue
        if not 14 <= dte <= 28:
            continue
        if not Decimal("0.15") <= abs(contract.delta) <= Decimal("0.30"):
            continue
        if contract.open_interest <= Decimal("100"):
            continue
        if not Decimal("0.04") < annualized_yield < Decimal("1.00"):
            continue
        if score <= Decimal("0.05"):
            continue
        eligible.append((score, contract.symbol, contract))

    return max(eligible, default=(None, "", None), key=lambda item: (item[0], item[1]))[2]


def _position_strike(symbol: str) -> Decimal:
    try:
        return Decimal(symbol[-8:]) / Decimal("1000")
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"cannot determine strike from option symbol {symbol!r}") from exc


def build_reservations(
    equities: tuple[EquityPosition, ...],
    options: tuple[OptionPosition, ...],
    orders: tuple[OptionOpenOrder, ...],
) -> WheelReservations:
    long_shares: dict[str, Decimal] = {}
    for equity in equities:
        long_shares[equity.symbol] = long_shares.get(equity.symbol, Decimal(0)) + equity.qty

    put_collateral: dict[str, Decimal] = {}
    covered_shares: dict[str, Decimal] = {}
    active_qty: dict[str, Decimal] = {}

    def reserve(underlying: str, kind: str, qty: Decimal, strike: Decimal | None) -> None:
        if qty <= 0:
            return
        if qty > Decimal(1):
            raise ValueError(f"wheel quantity exceeds one contract for {underlying}")
        active_qty[underlying] = active_qty.get(underlying, Decimal(0)) + qty
        if active_qty[underlying] > Decimal(1):
            raise ValueError(f"multiple active wheel contracts for {underlying}")
        if kind == "put":
            if strike is None or strike <= 0:
                raise ValueError(f"invalid put strike for {underlying}")
            put_collateral[underlying] = (
                put_collateral.get(underlying, Decimal(0)) + strike * CONTRACT_MULTIPLIER * qty
            )
        elif kind == "call":
            shares = CONTRACT_MULTIPLIER * qty
            covered_shares[underlying] = covered_shares.get(underlying, Decimal(0)) + shares
        else:
            raise ValueError(f"unsupported option kind {kind!r}")

    for position in options:
        if position.qty < 0:
            reserve(
                position.underlying,
                position.kind.casefold(),
                abs(position.qty),
                _position_strike(position.symbol) if position.kind.casefold() == "put" else None,
            )

    for order in orders:
        if order.position_intent.casefold() != "sell_to_open":
            continue
        remaining = order.qty - order.filled_qty
        if remaining < 0:
            raise ValueError(f"filled quantity exceeds order quantity for {order.symbol}")
        reserve(order.underlying, order.kind.casefold(), remaining, order.strike)

    for underlying, shares in covered_shares.items():
        if long_shares.get(underlying, Decimal(0)) < shares:
            raise ValueError(f"short call is not covered for {underlying}")

    return WheelReservations(put_collateral=put_collateral, covered_shares=covered_shares)


def option_delta_exposure(
    positions: tuple[OptionPosition, ...],
    spot_prices: dict[str, Decimal],
) -> dict[str, Decimal]:
    exposure: dict[str, Decimal] = {}
    for position in positions:
        amount = (
            position.qty * position.delta * CONTRACT_MULTIPLIER * spot_prices[position.underlying]
        )
        exposure[position.underlying] = exposure.get(position.underlying, Decimal(0)) + amount
    return exposure


def option_intent_delta_exposure(
    intents: tuple[OptionIntent, ...],
    spot_prices: dict[str, Decimal],
) -> dict[str, Decimal]:
    exposure: dict[str, Decimal] = {}
    for intent in intents:
        sign = Decimal(1) if intent.side.casefold() == "buy" else Decimal(-1)
        amount = (
            sign * intent.qty * intent.delta * CONTRACT_MULTIPLIER * spot_prices[intent.underlying]
        )
        exposure[intent.underlying] = exposure.get(intent.underlying, Decimal(0)) + amount
    return exposure


def plan_profit_exit(
    position: OptionPosition,
    contract: OptionContract,
    now: datetime,
) -> OptionIntent | None:
    if position.qty >= 0 or position.avg_entry_price <= 0:
        return None
    if position.symbol != contract.symbol or not _valid_quote(contract, now):
        return None
    if contract.ask > position.avg_entry_price * Decimal("0.50"):
        return None
    return OptionIntent(
        symbol=contract.symbol,
        underlying=contract.underlying,
        kind=contract.kind,
        side="buy",
        position_intent="buy_to_close",
        qty=abs(position.qty),
        limit_price=contract.ask,
        delta=contract.delta,
    )


def plan_new_entry(
    underlying: str,
    decision: str,
    equities: tuple[EquityPosition, ...],
    options: tuple[OptionPosition, ...],
    orders: tuple[OptionOpenOrder, ...],
    contracts: tuple[OptionContract, ...],
    now: datetime,
    earnings_date: date | None,
    available_cash: Decimal,
) -> OptionIntent | None:
    if any(position.underlying == underlying for position in options):
        return None
    if any(order.underlying == underlying for order in orders):
        return None

    reservations = build_reservations(equities, options, orders)
    active_underlyings = set(reservations.put_collateral) | set(reservations.covered_shares)
    if underlying in active_underlyings:
        return None

    signal = decision.strip().casefold()
    underlying_shares = sum(
        (equity.qty for equity in equities if equity.symbol == underlying), Decimal(0)
    )

    if signal in {"buy", "overweight"} and underlying_shares == 0:
        candidates = tuple(
            contract
            for contract in contracts
            if contract.underlying == underlying and contract.kind.casefold() == "put"
        )
        selected = select_contract(candidates, now, earnings_date)
        if selected is None or available_cash < selected.strike * CONTRACT_MULTIPLIER:
            return None
    elif signal in {"hold", "underweight"}:
        already_covered = reservations.covered_shares.get(underlying, Decimal(0))
        if underlying_shares - already_covered < CONTRACT_MULTIPLIER:
            return None
        covering_equities = tuple(
            equity for equity in equities if equity.symbol == underlying and equity.qty > 0
        )
        if not covering_equities or any(
            not equity.avg_entry_price.is_finite() or equity.avg_entry_price <= 0
            for equity in covering_equities
        ):
            return None
        total_long_shares = sum((equity.qty for equity in covering_equities), Decimal(0))
        cost_basis = (
            sum((equity.qty * equity.avg_entry_price for equity in covering_equities), Decimal(0))
            / total_long_shares
        )
        candidates = tuple(
            contract
            for contract in contracts
            if contract.underlying == underlying
            and contract.kind.casefold() == "call"
            and contract.strike >= cost_basis
        )
        selected = select_contract(candidates, now, earnings_date)
        if selected is None:
            return None
    else:
        return None

    return OptionIntent(
        symbol=selected.symbol,
        underlying=selected.underlying,
        kind=selected.kind,
        side="sell",
        position_intent="sell_to_open",
        qty=Decimal(1),
        limit_price=(selected.bid + selected.ask) / Decimal(2),
        delta=selected.delta,
    )
