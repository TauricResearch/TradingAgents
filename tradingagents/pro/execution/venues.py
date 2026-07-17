"""Venue definitions + the shared paper adapter (consolidation: five venues
are five VenueSpecs over one tested fill engine, not five adapters).

Live transports are deliberate stubs (Constraint 5): they raise
ExecutionNotEnabled with instructions. Wiring real credentials is a
sign-off event, not a code default.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from tradingagents.pro.backtest.costs import CommissionModel, SlippageModel
from tradingagents.pro.execution.interface import (
    AccountState,
    AdapterCapabilities,
    BracketSpec,
    BrokerPosition,
    ExecutionNotEnabled,
    OrderRequest,
    OrderResult,
    OrderSpec,
    OrderState,
    OrderUpdate,
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
    # multi-asset paper venue: the hourly loop's book covers the whole
    # tradeable universe (Phase 2 — mt5's gold-only map silently venue-
    # rejected every BTC order the judge approved)
    "paper": VenueSpec(
        name="paper",
        symbol_map={"XAUUSD": "XAUUSD", "BTC-USD": "BTCUSD",
                    "ETH-USD": "ETHUSD", "SOL-USD": "SOLUSD"},
        quantity_precision=4,
        min_quantity=0.0001,
        commission=CommissionModel(rate_bps=5),
        slippage=SlippageModel(bps=3),
    ),
    "binance": VenueSpec(
        name="binance",
        symbol_map={"BTC-USD": "BTCUSDT", "BTCUSDT": "BTCUSDT",
                    "ETH-USD": "ETHUSDT", "SOL-USD": "SOLUSDT"},
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

    With ``state_path`` set, the book (cash, positions, idempotency cache)
    persists atomically on every mutation and reloads on construction —
    the venue "remembers" across process restarts, exactly like a real
    broker, which is what makes ``service.rehydrate()`` meaningful in
    production paper mode. Default None keeps the in-memory behavior.
    """

    def __init__(self, venue: VenueSpec, starting_cash: float = 100_000.0,
                 state_path: str | Path | None = None):
        self.venue = venue
        self.name = f"paper:{venue.name}"
        self._cash = starting_cash
        self._positions: dict[str, BrokerPosition] = {}
        self._seen: dict[str, OrderResult] = {}
        self._orders: dict[str, OrderUpdate] = {}  # v2 book, by client_order_id
        self._state_path = Path(state_path) if state_path else None
        if self._state_path is not None:
            self._load_state()

    # --- durability ---------------------------------------------------------------

    def _load_state(self) -> None:
        assert self._state_path is not None
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except Exception:
            logging.getLogger(__name__).warning(
                "corrupt paper state %s; starting fresh book", self._state_path,
                exc_info=True,
            )
            return
        self._cash = raw["cash"]
        self._positions = {
            symbol: BrokerPosition(**data)
            for symbol, data in raw.get("positions", {}).items()
        }
        self._seen = {
            key: OrderResult(**data) for key, data in raw.get("seen", {}).items()
        }
        for key, data in raw.get("orders", {}).items():
            self._orders[key] = OrderUpdate(**{
                **data,
                "state": OrderState(data["state"]),
                "ts": datetime.fromisoformat(data["ts"]),
            })

    def _save_state(self) -> None:
        if self._state_path is None:
            return
        from tradingagents.pro.persistence import atomic_write_json

        atomic_write_json(self._state_path, {
            "cash": self._cash,
            "positions": {s: asdict(p) for s, p in self._positions.items()},
            "seen": {k: asdict(r) for k, r in self._seen.items()},
            "orders": {
                k: {**asdict(u), "state": u.state.value, "ts": u.ts.isoformat()}
                for k, u in self._orders.items()
            },
        })

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
        self._save_state()
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
        self._save_state()
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

    # --- v2 contract (VenueAdapter) --------------------------------------------------
    # Paper is the degenerate async case: every order goes terminal inside
    # place_order, which is what lets one conformance suite cover paper and
    # live implementations alike.

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            native_bracket=False,
            terminal_on_place=True,
            supports_client_oid_lookup=True,
            supports_streams=False,
        )

    def _v2_update(self, spec: OrderSpec, state: OrderState, *,
                   filled: float = 0.0, price: float = 0.0, fee: float = 0.0,
                   reason: str = "") -> OrderUpdate:
        update = OrderUpdate(
            client_order_id=spec.client_order_id, state=state,
            venue_order_id=f"paper-{len(self._orders) + 1}",
            filled_quantity=filled, avg_fill_price=price,
            commission=fee, reason=reason,
        )
        self._orders[spec.client_order_id] = update
        self._save_state()
        return update

    def place_order(self, spec: OrderSpec,
                    bracket: BracketSpec | None = None) -> OrderUpdate:
        if spec.client_order_id in self._orders:
            return self._orders[spec.client_order_id]  # venue-side dedupe
        try:
            self.venue.venue_symbol(spec.symbol)
        except ValueError as exc:
            return self._v2_update(spec, OrderState.REJECTED, reason=str(exc))
        quantity = round(spec.quantity, self.venue.quantity_precision)
        if quantity < self.venue.min_quantity or quantity <= 0:
            return self._v2_update(
                spec, OrderState.REJECTED,
                reason=f"quantity {quantity} below venue minimum "
                       f"{self.venue.min_quantity}",
            )
        reference = (spec.limit_price if spec.order_type == "limit"
                     and spec.limit_price else spec.reference_price)
        fill_price = self.venue.slippage.fill_price(reference, spec.side)
        fee = self.venue.commission.cost(quantity, fill_price)

        if spec.reduce_only:
            position = self._positions.get(spec.symbol)
            if position is None or position.side == spec.side:
                return self._v2_update(
                    spec, OrderState.REJECTED,
                    reason=f"reduce-only with no opposing position in {spec.symbol}",
                )
            close_qty = min(quantity, position.quantity)
            sign = 1 if spec.side == "BUY" else -1
            self._cash -= sign * close_qty * fill_price + fee
            remaining = round(position.quantity - close_qty,
                              self.venue.quantity_precision)
            if remaining > 0:
                self._positions[spec.symbol] = BrokerPosition(
                    symbol=position.symbol, side=position.side,
                    quantity=remaining, avg_price=position.avg_price,
                )
            else:
                self._positions.pop(spec.symbol, None)
            return self._v2_update(spec, OrderState.FILLED, filled=close_qty,
                                   price=fill_price, fee=fee)

        sign = 1 if spec.side == "BUY" else -1
        self._cash -= sign * quantity * fill_price + fee
        self._positions[spec.symbol] = BrokerPosition(
            symbol=spec.symbol, side=spec.side, quantity=quantity,
            avg_price=fill_price,
        )
        return self._v2_update(spec, OrderState.FILLED, filled=quantity,
                               price=fill_price, fee=fee)

    def cancel_order(self, client_order_id: str) -> OrderUpdate:
        known = self._orders.get(client_order_id)
        if known is None:
            return OrderUpdate(client_order_id=client_order_id,
                               state=OrderState.REJECTED,
                               reason="unknown order")
        # everything is terminal on paper; canceling reports current truth
        return known

    def get_order(self, client_order_id: str) -> OrderUpdate | None:
        return self._orders.get(client_order_id)

    def open_orders(self) -> list[OrderUpdate]:
        return [u for u in self._orders.values() if not u.state.terminal]

    def poll_updates(self, since: datetime) -> list[OrderUpdate]:
        return sorted((u for u in self._orders.values() if u.ts >= since),
                      key=lambda u: u.ts)


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

    # v2 surface refuses identically: arming live is a sign-off event
    def capabilities(self) -> AdapterCapabilities:
        self._refuse()

    def place_order(self, spec: OrderSpec,
                    bracket: BracketSpec | None = None) -> OrderUpdate:
        self._refuse()

    def cancel_order(self, client_order_id: str) -> OrderUpdate:
        self._refuse()

    def get_order(self, client_order_id: str) -> OrderUpdate | None:
        self._refuse()

    def open_orders(self) -> list[OrderUpdate]:
        self._refuse()

    def poll_updates(self, since: datetime) -> list[OrderUpdate]:
        self._refuse()

    def supported_symbols(self) -> set[str]:
        self._refuse()
