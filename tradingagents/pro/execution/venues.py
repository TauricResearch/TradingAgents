"""Venue definitions + the shared paper adapter (consolidation: five venues
are five VenueSpecs over one tested fill engine, not five adapters).

Live transports are deliberate stubs (Constraint 5): they raise
ExecutionNotEnabled with instructions. Wiring real credentials is a
sign-off event, not a code default.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tradingagents.pro.backtest.costs import CommissionModel, SlippageModel
from tradingagents.pro.execution.interface import (
    AccountState,
    BrokerPosition,
    ExecutionNotEnabled,
    OrderRequest,
    OrderResult,
)


@dataclass(frozen=True)
class VenueSpec:
    name: str
    symbol_map: dict[str, str]  # canonical -> venue convention
    quantity_precision: int = 4
    min_quantity: float = 0.0
    commission: CommissionModel = field(default_factory=CommissionModel)
    slippage: SlippageModel = field(default_factory=SlippageModel)

    def venue_symbol(self, symbol: str) -> str:
        if symbol not in self.symbol_map:
            raise ValueError(f"{self.name} does not support {symbol}")
        return self.symbol_map[symbol]


VENUES: dict[str, VenueSpec] = {
    "binance": VenueSpec(
        name="binance",
        symbol_map={"BTC-USD": "BTCUSDT", "BTCUSDT": "BTCUSDT"},
        quantity_precision=3,
        min_quantity=0.001,
        commission=CommissionModel(rate_bps=10),  # 0.1% taker
    ),
    "bybit": VenueSpec(
        name="bybit",
        symbol_map={"BTC-USD": "BTCUSDT", "BTCUSDT": "BTCUSDT"},
        quantity_precision=3,
        min_quantity=0.001,
        commission=CommissionModel(rate_bps=10),
    ),
    "mt5": VenueSpec(
        name="mt5",
        symbol_map={"XAUUSD": "XAUUSD"},
        quantity_precision=2,
        min_quantity=0.01,
        commission=CommissionModel(rate_bps=0),  # spread-cost venue
        slippage=SlippageModel(bps=3),
    ),
    "ibkr": VenueSpec(
        name="ibkr",
        symbol_map={"XAUUSD": "GC", "BTC-USD": "BRR"},
        quantity_precision=0,
        min_quantity=1.0,
        commission=CommissionModel(rate_bps=0.5, minimum=2.0),
    ),
    "oanda": VenueSpec(
        name="oanda",
        symbol_map={"XAUUSD": "XAU_USD"},
        quantity_precision=0,
        min_quantity=1.0,
        commission=CommissionModel(rate_bps=0),
        slippage=SlippageModel(bps=4),
    ),
}


class PaperVenueAdapter:
    """Simulated venue honoring the shared execution interface.

    Idempotency lives here too (defense in depth alongside the router): a
    repeated idempotency key returns the original fill as 'duplicate'.
    """

    def __init__(self, venue: VenueSpec, starting_cash: float = 100_000.0):
        self.venue = venue
        self.name = f"paper:{venue.name}"
        self._cash = starting_cash
        self._positions: dict[str, BrokerPosition] = {}
        self._seen: dict[str, OrderResult] = {}

    def supported_symbols(self) -> set[str]:
        return set(self.venue.symbol_map)

    def submit(self, order: OrderRequest) -> OrderResult:
        if order.idempotency_key in self._seen:
            original = self._seen[order.idempotency_key]
            return OrderResult(
                status="duplicate",
                idempotency_key=order.idempotency_key,
                venue=self.name,
                venue_symbol=original.venue_symbol,
                filled_quantity=original.filled_quantity,
                fill_price=original.fill_price,
                reason="idempotency key already filled",
            )
        try:
            venue_symbol = self.venue.venue_symbol(order.symbol)
        except ValueError as exc:
            return OrderResult(
                status="rejected", idempotency_key=order.idempotency_key,
                venue=self.name, reason=str(exc),
            )
        quantity = round(order.quantity, self.venue.quantity_precision)
        if quantity < self.venue.min_quantity or quantity <= 0:
            return OrderResult(
                status="rejected", idempotency_key=order.idempotency_key,
                venue=self.name, venue_symbol=venue_symbol,
                reason=f"quantity {quantity} below venue minimum "
                       f"{self.venue.min_quantity}",
            )
        fill_price = self.venue.slippage.fill_price(order.reference_price, order.side)
        fee = self.venue.commission.cost(quantity, fill_price)
        self._cash -= fee
        sign = 1 if order.side == "BUY" else -1
        self._cash -= sign * quantity * fill_price
        self._positions[order.symbol] = BrokerPosition(
            symbol=order.symbol, side=order.side, quantity=quantity,
            avg_price=fill_price,
        )
        result = OrderResult(
            status="filled", idempotency_key=order.idempotency_key,
            venue=self.name, venue_symbol=venue_symbol,
            filled_quantity=quantity, fill_price=fill_price, commission=fee,
        )
        self._seen[order.idempotency_key] = result
        return result

    def close_position(self, symbol: str, reference_price: float) -> OrderResult:
        position = self._positions.pop(symbol, None)
        if position is None:
            return OrderResult(
                status="rejected", idempotency_key=f"close:{symbol}",
                venue=self.name, reason=f"no open position in {symbol}",
            )
        exit_side = "SELL" if position.side == "BUY" else "BUY"
        fill_price = self.venue.slippage.fill_price(reference_price, exit_side)
        fee = self.venue.commission.cost(position.quantity, fill_price)
        sign = 1 if exit_side == "BUY" else -1
        self._cash -= sign * position.quantity * fill_price
        self._cash -= fee
        return OrderResult(
            status="filled", idempotency_key=f"close:{symbol}",
            venue=self.name, venue_symbol=self.venue.venue_symbol(symbol),
            filled_quantity=position.quantity, fill_price=fill_price, commission=fee,
        )

    def positions(self) -> list[BrokerPosition]:
        return list(self._positions.values())

    def account(self) -> AccountState:
        mark = sum(
            (1 if p.side == "BUY" else -1) * p.quantity * p.avg_price
            for p in self._positions.values()
        )
        return AccountState(
            venue=self.name, equity=self._cash + mark, cash=self._cash,
            positions=tuple(self._positions.values()),
        )


class LiveAdapterStub:
    """Placeholder for a real transport. Instantiable (so wiring can be
    written and tested) but every operation refuses."""

    def __init__(self, venue: VenueSpec):
        self.venue = venue
        self.name = f"live:{venue.name}"

    def _refuse(self):
        raise ExecutionNotEnabled(
            f"live transport for {self.venue.name} is not wired (Phase 9 ships "
            "paper-only per Constraint 5); supplying credentials is an explicit "
            "sign-off event"
        )

    def submit(self, order: OrderRequest) -> OrderResult:
        self._refuse()

    def close_position(self, symbol: str, reference_price: float) -> OrderResult:
        self._refuse()

    def positions(self) -> list[BrokerPosition]:
        self._refuse()

    def account(self) -> AccountState:
        self._refuse()
