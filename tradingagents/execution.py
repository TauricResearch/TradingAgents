import hashlib
import importlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Protocol

from tradingagents.allocation import OrderIntent
from tradingagents.options import (
    EquityPosition,
    OptionContract,
    OptionIntent,
    OptionOpenOrder,
    OptionPosition,
)

LIVE_ACKNOWLEDGMENT = "I_UNDERSTAND_LIVE_ORDERS"
LIVE_OPTIONS_ACKNOWLEDGMENT = "I_UNDERSTAND_LIVE_OPTIONS"


@dataclass(frozen=True)
class AccountSnapshot:
    cash: Decimal
    buying_power: Decimal
    trading_blocked: bool
    status: str
    equity: Decimal = Decimal("0")
    options_buying_power: Decimal = Decimal("0")


@dataclass(frozen=True)
class AssetInfo:
    symbol: str
    asset_class: str
    tradable: bool
    shortable: bool
    fractionable: bool
    min_order_size: Decimal
    min_trade_increment: Decimal


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    market_value: Decimal


@dataclass(frozen=True)
class BrokerOpenOrder:
    symbol: str
    side: str
    qty: Decimal
    filled_qty: Decimal


@dataclass(frozen=True)
class OrderRequestSpec:
    symbol: str
    qty: Decimal
    side: str
    time_in_force: str
    client_order_id: str


@dataclass(frozen=True)
class OptionOrderRequestSpec:
    symbol: str
    qty: Decimal
    side: str
    position_intent: str
    limit_price: Decimal
    time_in_force: str
    client_order_id: str


class Broker(Protocol):
    def broker_time(self) -> datetime: ...

    def equity_market_is_open(self) -> bool: ...

    def account(self) -> AccountSnapshot: ...

    def asset(self, symbol: str) -> AssetInfo: ...

    def positions(self) -> dict[str, Decimal]: ...

    def open_order_exposure(self, prices: Mapping[str, Decimal]) -> dict[str, Decimal]: ...

    def latest_price(self, symbol: str) -> Decimal: ...

    def daily_closes(
        self, symbols: tuple[str, ...], limit: int = 61
    ) -> dict[str, tuple[tuple[date, Decimal], ...]]: ...

    def option_contract(self, symbol: str, now: datetime) -> OptionContract: ...

    def submit(self, spec: OrderRequestSpec) -> str: ...

    def find_order_by_client_id(self, client_order_id: str) -> str | None: ...


def validate_execution_mode(mode: str, auto_execute: bool, live_ack: str) -> None:
    if mode not in ("paper", "live"):
        raise ValueError("execution mode must be paper or live")
    if mode == "live" and auto_execute and live_ack != LIVE_ACKNOWLEDGMENT:
        raise ValueError("live acknowledgment is required for automatic live orders")


def alpaca_symbol(symbol: str) -> str:
    if symbol.endswith("-USD"):
        return f"{symbol[:-4]}/USD"
    return symbol


def _internal_symbol(symbol: str) -> str:
    if symbol.endswith("/USD"):
        return f"{symbol[:-4]}-USD"
    return symbol


def _enum_text(value) -> str:
    return str(getattr(value, "value", value))


def _decimal(value, default: str = "0") -> Decimal:
    if value is None:
        value = default
    return Decimal(str(value))


def _required_decimal(value, message: str) -> Decimal:
    if value is None:
        raise RuntimeError(message)
    try:
        result = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError) as error:
        raise RuntimeError(message) from error
    if not result.is_finite():
        raise RuntimeError(message)
    return result


def _required_text(value, message: str) -> str:
    if value is None:
        raise RuntimeError(message)
    try:
        result = _enum_text(value).strip()
    except (AttributeError, TypeError, ValueError) as error:
        raise RuntimeError(message) from error
    if not result:
        raise RuntimeError(message)
    return result


def _alpaca_class(module: str, name: str):
    try:
        return getattr(importlib.import_module(module), name)
    except ImportError as error:
        raise RuntimeError(
            'Alpaca support is not installed; install "tradingagents[alpaca]"'
        ) from error


def _trading_client_class():
    return _alpaca_class("alpaca.trading.client", "TradingClient")


def _market_order_request_class():
    return _alpaca_class("alpaca.trading.requests", "MarketOrderRequest")


def _limit_order_request_class():
    return _alpaca_class("alpaca.trading.requests", "LimitOrderRequest")


def _position_intent_class():
    return _alpaca_class("alpaca.trading.enums", "PositionIntent")


def _get_option_contracts_request_class():
    return _alpaca_class("alpaca.trading.requests", "GetOptionContractsRequest")


def _asset_status_class():
    return _alpaca_class("alpaca.trading.enums", "AssetStatus")


def _contract_type_class():
    return _alpaca_class("alpaca.trading.enums", "ContractType")


def _stock_data_client_class():
    return _alpaca_class("alpaca.data.historical.stock", "StockHistoricalDataClient")


def _crypto_data_client_class():
    return _alpaca_class("alpaca.data.historical.crypto", "CryptoHistoricalDataClient")


def _option_data_client_class():
    return _alpaca_class("alpaca.data.historical.option", "OptionHistoricalDataClient")


def _stock_latest_trade_request_class():
    return _alpaca_class("alpaca.data.requests", "StockLatestTradeRequest")


def _stock_bars_request_class():
    return _alpaca_class("alpaca.data.requests", "StockBarsRequest")


def _stock_timeframe_day():
    return _alpaca_class("alpaca.data.timeframe", "TimeFrame").Day


def _stock_data_feed_iex():
    return _alpaca_class("alpaca.data.enums", "DataFeed").IEX


def _crypto_latest_trade_request_class():
    return _alpaca_class("alpaca.data.requests", "CryptoLatestTradeRequest")


def _option_snapshot_request_class():
    return _alpaca_class("alpaca.data.requests", "OptionSnapshotRequest")


_OPTION_SYMBOL = re.compile(
    r"^(?P<underlying>[A-Z0-9.]{1,6})(?P<expiration>\d{6})(?P<kind>[CP])(?P<strike>\d{8})$"
)


def _option_symbol_parts(symbol: str) -> tuple[str, str, Decimal]:
    match = _OPTION_SYMBOL.fullmatch(symbol)
    if match is None:
        raise ValueError(f"invalid OCC option symbol {symbol!r}")
    kind = "call" if match.group("kind") == "C" else "put"
    strike = Decimal(match.group("strike")) / Decimal("1000")
    return match.group("underlying"), kind, strike


class AlpacaBroker:
    def __init__(
        self,
        key: str,
        secret: str,
        mode: str,
        client=None,
        live_ack: str = "",
        live_options_ack: str = "",
    ):
        validate_execution_mode(mode, auto_execute=False, live_ack="")
        if not key or not secret:
            raise RuntimeError("Alpaca credentials are required")

        self._key = key
        self._secret = secret
        self._mode = mode
        self._live_ack = live_ack
        self._live_options_ack = live_options_ack
        self._client = client
        if self._client is None:
            self._client = _trading_client_class()(key, secret, paper=mode == "paper")
        self._stock_data_client = None
        self._crypto_data_client = None
        self._option_data_client = None

    def broker_time(self) -> datetime:
        return self._client.get_clock().timestamp

    def equity_market_is_open(self) -> bool:
        return bool(self._client.get_clock().is_open)

    def account(self) -> AccountSnapshot:
        raw = self._client.get_account()
        status = _enum_text(raw.status)
        blocked = any(
            bool(getattr(raw, field, False))
            for field in (
                "trading_blocked",
                "account_blocked",
                "trade_suspended_by_user",
            )
        )
        if blocked:
            raise RuntimeError("Alpaca account is blocked from trading")
        if status.upper() != "ACTIVE":
            raise RuntimeError("Alpaca account is not active")
        account_values_error = "Alpaca account values are unavailable"
        cash = _required_decimal(getattr(raw, "cash", None), account_values_error)
        equity = _required_decimal(getattr(raw, "equity", None), account_values_error)
        buying_power = _required_decimal(
            getattr(raw, "buying_power", None), account_values_error
        )
        options_buying_power = _required_decimal(
            getattr(raw, "options_buying_power", None), account_values_error
        )
        if equity <= 0 or buying_power < 0 or options_buying_power < 0:
            raise RuntimeError(account_values_error)
        return AccountSnapshot(
            cash=cash,
            buying_power=buying_power,
            trading_blocked=False,
            status=status,
            equity=equity,
            options_buying_power=options_buying_power,
        )

    def asset(self, symbol: str) -> AssetInfo:
        raw = self._client.get_asset(alpaca_symbol(symbol))
        asset_class = _enum_text(raw.asset_class)
        fractionable = bool(raw.fractionable)
        fallback_increment = "0.001" if fractionable else "1"
        increment = _decimal(raw.min_trade_increment, fallback_increment)
        minimum = _decimal(raw.min_order_size, str(increment))
        active = _enum_text(getattr(raw, "status", "active")).lower() == "active"
        return AssetInfo(
            symbol=raw.symbol,
            asset_class=asset_class,
            tradable=active and bool(raw.tradable),
            shortable=bool(raw.shortable),
            fractionable=fractionable,
            min_order_size=minimum,
            min_trade_increment=increment,
        )

    def positions(self) -> dict[str, Decimal]:
        positions = {}
        for raw in self._client.get_all_positions():
            side = _enum_text(raw.side).lower()
            if raw.market_value is None:
                raise RuntimeError(f"Alpaca position market value is unavailable for {raw.symbol}")
            value = abs(_decimal(raw.market_value))
            if side == "short":
                value = -value
            elif side != "long":
                raise RuntimeError(f"unsupported Alpaca position side: {side}")
            position = BrokerPosition(_internal_symbol(raw.symbol), value)
            positions[position.symbol] = position.market_value
        return positions

    def open_order_exposure(self, prices: Mapping[str, Decimal]) -> dict[str, Decimal]:
        exposure: dict[str, Decimal] = {}
        for raw in self._client.get_orders():
            symbol = _internal_symbol(raw.symbol)
            if symbol not in prices:
                continue
            raw_qty = getattr(raw, "qty", None)
            raw_filled_qty = getattr(raw, "filled_qty", None)
            if raw_filled_qty is None:
                raise RuntimeError(f"remaining exposure is unavailable for open order {symbol}")
            order = BrokerOpenOrder(
                symbol=symbol,
                side=_enum_text(raw.side).lower(),
                qty=_decimal(raw_qty),
                filled_qty=_decimal(raw_filled_qty),
            )
            notional = getattr(raw, "notional", None)
            if raw_qty is not None:
                if order.symbol not in prices:
                    continue
                remaining_qty = order.qty - order.filled_qty
                if remaining_qty < 0:
                    raise RuntimeError(f"remaining exposure is invalid for open order {symbol}")
                remaining_notional = remaining_qty * _decimal(prices[order.symbol])
            elif notional is not None:
                original_notional = abs(_decimal(notional))
                if order.filled_qty == 0:
                    remaining_notional = original_notional
                else:
                    filled_avg_price = getattr(raw, "filled_avg_price", None)
                    if filled_avg_price is None:
                        raise RuntimeError(
                            f"remaining exposure is unavailable for open order {symbol}"
                        )
                    filled_value = order.filled_qty * _decimal(filled_avg_price)
                    remaining_notional = original_notional - filled_value
                    if remaining_notional < 0:
                        raise RuntimeError(f"remaining exposure is invalid for open order {symbol}")
            else:
                raise RuntimeError(f"remaining exposure is unavailable for open order {symbol}")
            if order.side == "sell":
                remaining_notional = -remaining_notional
            elif order.side != "buy":
                raise RuntimeError(f"unsupported Alpaca order side: {order.side}")
            exposure[order.symbol] = exposure.get(order.symbol, Decimal("0")) + remaining_notional
        return exposure

    def latest_price(self, symbol: str) -> Decimal:
        sdk_symbol = alpaca_symbol(symbol)
        generic_latest_trade = getattr(self._client, "get_latest_trade", None)
        if generic_latest_trade is not None:
            return self._trade_price(generic_latest_trade(sdk_symbol), sdk_symbol)

        if self.asset(symbol).asset_class == "crypto":
            if self._crypto_data_client is None:
                self._crypto_data_client = _crypto_data_client_class()(self._key, self._secret)
            request = _crypto_latest_trade_request_class()(symbol_or_symbols=sdk_symbol)
            trades = self._crypto_data_client.get_crypto_latest_trade(request)
        else:
            if self._stock_data_client is None:
                self._stock_data_client = _stock_data_client_class()(self._key, self._secret)
            request = _stock_latest_trade_request_class()(symbol_or_symbols=sdk_symbol)
            trades = self._stock_data_client.get_stock_latest_trade(request)
        return self._trade_price(trades, sdk_symbol)

    def daily_closes(
        self, symbols: tuple[str, ...], limit: int = 61
    ) -> dict[str, tuple[tuple[date, Decimal], ...]]:
        if self._stock_data_client is None:
            self._stock_data_client = _stock_data_client_class()(self._key, self._secret)
        request = _stock_bars_request_class()(
            symbol_or_symbols=list(symbols),
            timeframe=_stock_timeframe_day(),
            limit=limit,
            feed=_stock_data_feed_iex(),
        )
        response = self._stock_data_client.get_stock_bars(request)
        raw_history = getattr(response, "data", None)
        if not isinstance(raw_history, Mapping):
            raise RuntimeError("Alpaca daily bars response is unavailable")
        reference_time = self.broker_time()
        if not isinstance(reference_time, datetime) or reference_time.utcoffset() is None:
            raise RuntimeError("Alpaca broker time must be timezone-aware")

        history = {}
        for symbol in symbols:
            bars = raw_history.get(symbol)
            if not bars:
                raise RuntimeError(f"Alpaca daily bars are unavailable for {symbol}")
            rows = []
            for bar in bars:
                try:
                    close = Decimal(str(bar.close))
                    timestamp = bar.timestamp
                except (ArithmeticError, AttributeError, ValueError) as error:
                    raise RuntimeError(f"Alpaca daily bar is invalid for {symbol}") from error
                if (
                    not close.is_finite()
                    or close <= 0
                    or not isinstance(timestamp, datetime)
                    or timestamp.utcoffset() is None
                ):
                    raise RuntimeError(f"Alpaca daily bar is invalid for {symbol}")
                try:
                    day = timestamp.date()
                except (AttributeError, ValueError) as error:
                    raise RuntimeError(f"Alpaca daily bar is invalid for {symbol}") from error
                if not isinstance(day, date) or isinstance(day, datetime):
                    raise RuntimeError(f"Alpaca daily bar is invalid for {symbol}")
                rows.append((day, close))
            if (reference_time.date() - max(day for day, _close in rows)).days > 7:
                raise RuntimeError(f"Alpaca daily bars are stale for {symbol}")
            history[symbol] = tuple(rows)
        return history

    def option_snapshot(
        self, symbols: tuple[str, ...] | list[str]
    ) -> dict[str, tuple[Decimal, Decimal, Decimal, datetime]]:
        requested = list(symbols)
        if not requested:
            return {}
        if self._option_data_client is None:
            self._option_data_client = _option_data_client_class()(self._key, self._secret)
        request = _option_snapshot_request_class()(symbol_or_symbols=requested)
        response = self._option_data_client.get_option_snapshot(request)
        raw_snapshots = getattr(response, "data", response)
        if not isinstance(raw_snapshots, Mapping):
            raise RuntimeError("Alpaca option snapshot response is unavailable")

        snapshots = {}
        for symbol in requested:
            raw = raw_snapshots.get(symbol)
            if raw is None:
                raise RuntimeError("Alpaca option snapshot is incomplete")
            greeks = getattr(raw, "greeks", None)
            quote = getattr(raw, "latest_quote", None)
            delta_value = getattr(greeks, "delta", None) if greeks is not None else None
            bid_value = getattr(quote, "bid_price", None) if quote is not None else None
            ask_value = getattr(quote, "ask_price", None) if quote is not None else None
            quote_time = getattr(quote, "timestamp", None) if quote is not None else None
            if not isinstance(quote_time, datetime) or quote_time.utcoffset() is None:
                raise RuntimeError("Alpaca option snapshot is incomplete")
            snapshots[symbol] = (
                _required_decimal(delta_value, "Alpaca option snapshot is incomplete"),
                _required_decimal(bid_value, "Alpaca option snapshot is incomplete"),
                _required_decimal(ask_value, "Alpaca option snapshot is incomplete"),
                quote_time,
            )
        return snapshots

    def option_contracts(
        self, underlying: str, kind: str, now: datetime
    ) -> tuple[OptionContract, ...]:
        normalized_kind = kind.casefold()
        if normalized_kind not in ("call", "put"):
            raise ValueError("option kind must be call or put")
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ValueError("option contract lookup time must be timezone-aware")

        start = now.date() + timedelta(days=14)
        end = now.date() + timedelta(days=28)
        raw_contracts = []
        page_token = None
        while True:
            fields = {
                "underlying_symbols": [underlying],
                "status": _asset_status_class()("active"),
                "expiration_date_gte": start,
                "expiration_date_lte": end,
                "type": _contract_type_class()(normalized_kind),
            }
            if page_token is not None:
                fields["page_token"] = page_token
            request = _get_option_contracts_request_class()(**fields)
            response = self._client.get_option_contracts(request)
            page = getattr(response, "option_contracts", None)
            if page is None and isinstance(response, Mapping):
                page = response.get("option_contracts")
            if page is None:
                raise RuntimeError("Alpaca option contracts response is unavailable")
            raw_contracts.extend(page)
            page_token = getattr(response, "next_page_token", None)
            if page_token is None and isinstance(response, Mapping):
                page_token = response.get("next_page_token")
            if not page_token:
                break

        validated_contracts = []
        for raw in raw_contracts:
            try:
                symbol = _required_text(
                    getattr(raw, "symbol", None), "Alpaca option contract is malformed"
                )
                returned_underlying = str(raw.underlying_symbol)
                returned_kind = _enum_text(raw.type).casefold()
                returned_status = _enum_text(raw.status).casefold()
                expiration = raw.expiration_date
                strike = _required_decimal(
                    raw.strike_price, "Alpaca option contract is malformed"
                )
                open_interest = _required_decimal(
                    raw.open_interest, "Alpaca option contract is malformed"
                )
                occ_underlying, occ_kind, occ_strike = _option_symbol_parts(symbol)
                occ_expiration = datetime.strptime(
                    _OPTION_SYMBOL.fullmatch(symbol).group("expiration"), "%y%m%d"
                ).date()
            except RuntimeError:
                raise
            except (AttributeError, TypeError, ValueError) as error:
                raise RuntimeError("Alpaca option contract is malformed") from error
            if (
                returned_underlying != underlying
                or returned_kind != normalized_kind
                or returned_status != "active"
                or not isinstance(expiration, date)
                or isinstance(expiration, datetime)
                or not start <= expiration <= end
                or occ_underlying != underlying
                or occ_kind != normalized_kind
                or occ_strike != strike
                or occ_expiration != expiration
                or strike <= 0
                or open_interest < 0
            ):
                raise RuntimeError("Alpaca returned an inconsistent option contract")
            validated_contracts.append(
                (symbol, returned_underlying, returned_kind, strike, expiration, open_interest)
            )

        snapshots = self.option_snapshot([item[0] for item in validated_contracts])
        contracts = []
        for symbol, returned_underlying, returned_kind, strike, expiration, open_interest in (
            validated_contracts
        ):
            delta, bid, ask, quote_time = snapshots[symbol]
            contracts.append(
                OptionContract(
                    symbol=symbol,
                    underlying=returned_underlying,
                    kind=returned_kind,
                    strike=strike,
                    expiration=expiration,
                    delta=delta,
                    bid=bid,
                    ask=ask,
                    open_interest=open_interest,
                    quote_time=quote_time,
                )
            )
        return tuple(contracts)

    def option_contract(self, symbol: str, now: datetime) -> OptionContract:
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ValueError("option contract lookup time must be timezone-aware")
        underlying, kind, strike = _option_symbol_parts(symbol)
        expiration = datetime.strptime(
            _OPTION_SYMBOL.fullmatch(symbol).group("expiration"), "%y%m%d"
        ).date()
        delta, bid, ask, quote_time = self.option_snapshot((symbol,))[symbol]
        return OptionContract(
            symbol,
            underlying,
            kind,
            strike,
            expiration,
            delta,
            bid,
            ask,
            Decimal("0"),
            quote_time,
        )

    def wheel_positions_and_orders(
        self,
    ) -> tuple[
        tuple[EquityPosition, ...],
        tuple[OptionPosition, ...],
        tuple[OptionOpenOrder, ...],
    ]:
        raw_positions = self._client.get_all_positions()
        position_rows = []
        option_symbols = []
        for raw in raw_positions:
            try:
                asset_class = _enum_text(raw.asset_class).casefold()
                if asset_class not in {"us_equity", "us_option", "crypto"}:
                    raise RuntimeError("Alpaca position record is unclassifiable")
                if asset_class == "crypto":
                    continue
                symbol = _required_text(
                    getattr(raw, "symbol", None), "Alpaca position record is malformed"
                )
                side = _enum_text(raw.side).casefold()
                raw_qty = _required_decimal(
                    raw.qty, "Alpaca position record is malformed"
                )
                avg_entry_price = _required_decimal(
                    raw.avg_entry_price, "Alpaca position record is malformed"
                )
                current_price = _required_decimal(
                    raw.current_price, "Alpaca position record is malformed"
                )
                if side not in {"long", "short"}:
                    raise RuntimeError("Alpaca position record is malformed")
                if asset_class == "us_option":
                    if (
                        raw_qty == 0
                        or raw_qty != raw_qty.to_integral()
                        or (side == "short") != (raw_qty < 0)
                    ):
                        raise RuntimeError("Alpaca option position record is malformed")
                    qty = raw_qty
                else:
                    qty = abs(raw_qty)
                    if side == "short":
                        qty = -qty
                if qty == 0:
                    raise RuntimeError("Alpaca position record is malformed")
                position_rows.append(
                    (asset_class, symbol, qty, avg_entry_price, current_price)
                )
                if asset_class == "us_option":
                    _option_symbol_parts(symbol)
                    option_symbols.append(symbol)
            except RuntimeError:
                raise
            except (AttributeError, TypeError, ValueError) as error:
                raise RuntimeError("Alpaca position record is malformed") from error

        snapshots = self.option_snapshot(option_symbols)
        equities = []
        options = []
        for asset_class, symbol, qty, avg_entry_price, current_price in position_rows:
            if asset_class == "us_equity":
                equities.append(
                    EquityPosition(
                        symbol=symbol,
                        qty=qty,
                        avg_entry_price=avg_entry_price,
                        current_price=current_price,
                    )
                )
            else:
                underlying, kind, _strike = _option_symbol_parts(symbol)
                delta = snapshots[symbol][0]
                if delta is None:
                    raise RuntimeError("Alpaca option position delta is unavailable")
                options.append(
                    OptionPosition(
                        symbol=symbol,
                        underlying=underlying,
                        kind=kind,
                        qty=qty,
                        avg_entry_price=avg_entry_price,
                        delta=delta,
                    )
                )

        open_orders = []
        for raw in self._client.get_orders():
            try:
                asset_class = _enum_text(raw.asset_class).casefold()
            except (AttributeError, TypeError, ValueError) as error:
                raise RuntimeError("Alpaca order record is unclassifiable") from error
            if asset_class not in {"us_equity", "us_option", "crypto"}:
                raise RuntimeError("Alpaca order record is unclassifiable")
            if asset_class != "us_option":
                continue
            try:
                record_error = "Alpaca option order record is malformed"
                symbol = _required_text(getattr(raw, "symbol", None), record_error)
                underlying, kind, strike = _option_symbol_parts(symbol)
                position_intent = _required_text(
                    getattr(raw, "position_intent", None), record_error
                ).casefold()
                if position_intent not in {
                    "buy_to_open",
                    "buy_to_close",
                    "sell_to_open",
                    "sell_to_close",
                }:
                    raise RuntimeError(record_error)
                order_id = _required_text(getattr(raw, "id", None), record_error)
                client_order_id = _required_text(
                    getattr(raw, "client_order_id", None), record_error
                )
                submitted_at = getattr(raw, "submitted_at", None)
                if not isinstance(submitted_at, datetime) or submitted_at.utcoffset() is None:
                    raise RuntimeError(record_error)
                qty = _required_decimal(getattr(raw, "qty", None), record_error)
                filled_qty = _required_decimal(getattr(raw, "filled_qty", None), record_error)
                if (
                    qty <= 0
                    or filled_qty < 0
                    or filled_qty > qty
                    or qty != qty.to_integral()
                    or filled_qty != filled_qty.to_integral()
                ):
                    raise RuntimeError(record_error)
                open_orders.append(
                    OptionOpenOrder(
                        symbol=symbol,
                        underlying=underlying,
                        kind=kind,
                        position_intent=position_intent,
                        qty=qty,
                        filled_qty=filled_qty,
                        strike=strike,
                        order_id=order_id,
                        client_order_id=client_order_id,
                        submitted_at=submitted_at,
                    )
                )
            except RuntimeError:
                raise
            except (AttributeError, TypeError, ValueError) as error:
                raise RuntimeError("Alpaca option order record is malformed") from error
        return tuple(equities), tuple(options), tuple(open_orders)

    @staticmethod
    def _trade_price(trades, symbol: str) -> Decimal:
        trade = trades[symbol] if isinstance(trades, Mapping) else trades
        price = _decimal(getattr(trade, "price", None))
        if price <= 0:
            raise RuntimeError(f"latest price is unavailable for {symbol}")
        return price

    def prepare_order(
        self,
        intent: OrderIntent,
        asset: AssetInfo,
        price: Decimal,
        cycle_id: str,
    ) -> OrderRequestSpec:
        sdk_symbol = alpaca_symbol(intent.symbol)
        if sdk_symbol != asset.symbol:
            raise ValueError("asset capabilities do not match the order symbol")
        if not asset.tradable:
            raise ValueError(f"asset {asset.symbol} is not tradable")
        if intent.side not in ("buy", "sell"):
            raise ValueError("order side must be buy or sell")
        if intent.target_notional < 0:
            if asset.asset_class == "crypto":
                raise ValueError("crypto assets are not shortable")
            if not asset.shortable:
                raise ValueError(f"asset {asset.symbol} is not shortable")

        price = _decimal(price)
        if price <= 0:
            raise ValueError("order price must be positive")
        if intent.notional <= 0:
            raise ValueError("order notional must be positive")
        increment = asset.min_trade_increment
        if not asset.fractionable or intent.target_notional < 0:
            increment = max(increment, Decimal("1"))
        if increment <= 0 or asset.min_order_size <= 0:
            raise ValueError("asset order increments must be positive")
        qty = (intent.notional / price / increment).to_integral_value(
            rounding=ROUND_DOWN
        ) * increment
        if qty < asset.min_order_size:
            raise ValueError("order quantity is below the asset minimum order size")

        if asset.asset_class == "crypto":
            time_in_force = "gtc"
        elif asset.asset_class == "us_equity":
            time_in_force = "day"
        else:
            raise ValueError(f"unsupported asset class: {asset.asset_class}")
        identity = "|".join((cycle_id, sdk_symbol, intent.side, str(intent.target_notional)))
        client_order_id = f"ta-{hashlib.sha256(identity.encode()).hexdigest()[:32]}"
        return OrderRequestSpec(
            symbol=sdk_symbol,
            qty=qty,
            side=intent.side,
            time_in_force=time_in_force,
            client_order_id=client_order_id,
        )

    def submit(self, spec: OrderRequestSpec) -> str:
        self._validate_submission()
        request = _market_order_request_class()(
            symbol=spec.symbol,
            qty=float(spec.qty),
            side=spec.side,
            time_in_force=spec.time_in_force,
            client_order_id=spec.client_order_id,
        )
        order = self._client.submit_order(order_data=request)
        order_id = getattr(order, "id", None)
        if order_id is None:
            raise RuntimeError("Alpaca submission returned no order ID")
        return str(order_id)

    def find_order_by_client_id(self, client_order_id: str) -> str | None:
        try:
            order = self._client.get_order_by_client_id(client_order_id)
        except Exception as error:
            if getattr(error, "status_code", None) == 404:
                return None
            raise
        if order is None:
            return None
        order_id = getattr(order, "id", None)
        if order_id is None:
            raise RuntimeError("Alpaca order lookup returned no order ID")
        return str(order_id)

    def submit_idempotent(self, spec: OrderRequestSpec) -> str:
        self._validate_submission()
        existing_order_id = self.find_order_by_client_id(spec.client_order_id)
        if existing_order_id is not None:
            return existing_order_id
        try:
            return self.submit(spec)
        except Exception as submission_error:
            existing_order_id = self.find_order_by_client_id(spec.client_order_id)
            if existing_order_id is not None:
                return existing_order_id
            raise submission_error

    def prepare_option_order(self, intent: OptionIntent, cycle_id: str) -> OptionOrderRequestSpec:
        underlying, kind, _strike = _option_symbol_parts(intent.symbol)
        if underlying != intent.underlying or kind != intent.kind.casefold():
            raise ValueError("option contract does not match intent metadata")
        if intent.side not in ("buy", "sell"):
            raise ValueError("option order side must be buy or sell")
        allowed_intents = {
            "buy": {"buy_to_open", "buy_to_close"},
            "sell": {"sell_to_open", "sell_to_close"},
        }
        if intent.position_intent not in allowed_intents[intent.side]:
            raise ValueError("option position intent does not match order side")
        if not intent.qty.is_finite() or intent.qty <= 0 or intent.qty != intent.qty.to_integral():
            raise ValueError("option quantity must be a positive whole number")
        if not intent.limit_price.is_finite() or intent.limit_price <= 0:
            raise ValueError("option limit price must be positive")
        identity = "|".join(
            (
                cycle_id,
                intent.symbol,
                intent.side,
                intent.position_intent,
                str(intent.qty),
                str(intent.limit_price),
            )
        )
        client_order_id = f"ta-wheel-{hashlib.sha256(identity.encode()).hexdigest()[:24]}"
        return OptionOrderRequestSpec(
            symbol=intent.symbol,
            qty=intent.qty,
            side=intent.side,
            position_intent=intent.position_intent,
            limit_price=intent.limit_price,
            time_in_force="day",
            client_order_id=client_order_id,
        )

    def submit_option_idempotent(self, spec: OptionOrderRequestSpec) -> str:
        self._validate_option_submission()
        if not spec.limit_price.is_finite() or spec.limit_price <= 0:
            raise ValueError("option limit price must be positive")
        if not spec.qty.is_finite() or spec.qty <= 0 or spec.qty != spec.qty.to_integral():
            raise ValueError("option quantity must be a positive whole number")
        if spec.time_in_force != "day":
            raise ValueError("option orders must use day time in force")
        if spec.side not in ("buy", "sell"):
            raise ValueError("option order side must be buy or sell")
        allowed_intents = {
            "buy": {"buy_to_open", "buy_to_close"},
            "sell": {"sell_to_open", "sell_to_close"},
        }
        if spec.position_intent not in allowed_intents[spec.side]:
            raise ValueError("option position intent does not match order side")
        _option_symbol_parts(spec.symbol)
        existing_order_id = self.find_order_by_client_id(spec.client_order_id)
        if existing_order_id is not None:
            return existing_order_id
        request = _limit_order_request_class()(
            symbol=spec.symbol,
            qty=float(spec.qty),
            side=spec.side,
            position_intent=_position_intent_class()(spec.position_intent),
            limit_price=float(spec.limit_price),
            time_in_force=spec.time_in_force,
            client_order_id=spec.client_order_id,
        )
        self._assert_trading_endpoint_matches_mode()
        try:
            order = self._client.submit_order(order_data=request)
        except Exception as submission_error:
            existing_order_id = self.find_order_by_client_id(spec.client_order_id)
            if existing_order_id is not None:
                return existing_order_id
            raise submission_error
        order_id = getattr(order, "id", None)
        if order_id is None:
            ambiguity = RuntimeError("Alpaca option submission result is ambiguous")
            try:
                existing_order_id = self.find_order_by_client_id(spec.client_order_id)
            except Exception:
                raise ambiguity from None
            if existing_order_id is not None:
                return existing_order_id
            raise ambiguity
        return str(order_id)

    def cancel_stale_option_order(self, order_id: str, client_order_id: str) -> None:
        if not client_order_id.startswith("ta-wheel-"):
            raise ValueError("option order is not owned by the wheel strategy")
        self._validate_option_submission()
        self._assert_trading_endpoint_matches_mode()
        self._client.cancel_order_by_id(order_id)

    def _assert_trading_endpoint_matches_mode(self) -> None:
        endpoint_error = "Alpaca trading endpoint cannot be verified"
        try:
            endpoint = _enum_text(getattr(self._client, "_base_url", None)).rstrip("/")
        except (AttributeError, TypeError, ValueError) as error:
            raise RuntimeError(endpoint_error) from error
        expected = {
            "paper": "https://paper-api.alpaca.markets",
            "live": "https://api.alpaca.markets",
        }[self._mode]
        if endpoint != expected:
            raise RuntimeError(endpoint_error)

    def _validate_option_submission(self) -> None:
        self._validate_submission()
        if self._mode == "live" and self._live_options_ack != LIVE_OPTIONS_ACKNOWLEDGMENT:
            raise ValueError("live options acknowledgment is required")

    def _validate_submission(self) -> None:
        validate_execution_mode(self._mode, auto_execute=True, live_ack=self._live_ack)
