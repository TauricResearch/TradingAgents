import hashlib
import importlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Protocol

from tradingagents.allocation import OrderIntent

LIVE_ACKNOWLEDGMENT = "I_UNDERSTAND_LIVE_ORDERS"


@dataclass(frozen=True)
class AccountSnapshot:
    cash: Decimal
    buying_power: Decimal
    trading_blocked: bool
    status: str


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


class Broker(Protocol):
    def broker_time(self) -> datetime: ...

    def equity_market_is_open(self) -> bool: ...

    def account(self) -> AccountSnapshot: ...

    def asset(self, symbol: str) -> AssetInfo: ...

    def positions(self) -> dict[str, Decimal]: ...

    def open_order_exposure(self, prices: Mapping[str, Decimal]) -> dict[str, Decimal]: ...

    def latest_price(self, symbol: str) -> Decimal: ...

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


def _stock_data_client_class():
    return _alpaca_class("alpaca.data.historical.stock", "StockHistoricalDataClient")


def _crypto_data_client_class():
    return _alpaca_class("alpaca.data.historical.crypto", "CryptoHistoricalDataClient")


def _stock_latest_trade_request_class():
    return _alpaca_class("alpaca.data.requests", "StockLatestTradeRequest")


def _crypto_latest_trade_request_class():
    return _alpaca_class("alpaca.data.requests", "CryptoLatestTradeRequest")


class AlpacaBroker:
    def __init__(self, key: str, secret: str, mode: str, client=None, live_ack: str = ""):
        validate_execution_mode(mode, auto_execute=False, live_ack="")
        if not key or not secret:
            raise RuntimeError("Alpaca credentials are required")

        self._key = key
        self._secret = secret
        self._mode = mode
        self._live_ack = live_ack
        self._client = client
        if self._client is None:
            self._client = _trading_client_class()(key, secret, paper=mode == "paper")
        self._stock_data_client = None
        self._crypto_data_client = None

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
        return AccountSnapshot(
            cash=_decimal(raw.cash),
            buying_power=_decimal(raw.buying_power),
            trading_blocked=False,
            status=status,
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
        if not asset.fractionable:
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

    def _validate_submission(self) -> None:
        validate_execution_mode(self._mode, auto_execute=True, live_ack=self._live_ack)
