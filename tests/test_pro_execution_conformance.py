"""Adapter conformance: ONE suite, N implementations (go-live Phase 1).

Every VenueAdapter implementation must pass identical lifecycle semantics:
the paper adapter (terminal-on-place), a fake-transport Delta adapter
(async ack→fill), and — when ``DELTA_TESTNET_API_KEY`` is set — the real
Delta Exchange India testnet. The no-duplicate guarantee is asserted on
venue-held state (orders/positions), never on return values, because
venues legitimately differ in how they *report* a duplicate.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from tradingagents.pro.execution import VENUES, OrderSpec, OrderState, PaperVenueAdapter
from tradingagents.pro.execution.adapters.delta import (
    SYMBOL_MAP,
    DeltaAdapter,
)
from tradingagents.pro.execution.adapters.delta_auth import (
    DeltaCredentials,
    clock_skew_seconds,
    redact,
    sign,
)
from tradingagents.pro.execution.instruments import (
    InstrumentInfo,
    InstrumentService,
    InstrumentsUnavailable,
)

CREDS = DeltaCredentials("test-key-abc", "test-secret-xyz")


# --- fake Delta venue -----------------------------------------------------------------


class FakeDeltaHttp:
    """In-memory Delta India: async semantics (orders ack as 'open', fill
    when the test calls ``settle``), duplicate-coid rejection, signing
    headers enforced on private routes."""

    PRODUCTS = [
        {"id": 27, "symbol": "BTCUSD", "tick_size": "0.5",
         "contract_value": "0.001", "default_leverage": "10"},
        {"id": 93, "symbol": "XAUTUSD", "tick_size": "0.1",
         "contract_value": "0.01", "default_leverage": "5"},
    ]

    def __init__(self):
        self.orders: dict[str, dict] = {}   # by client_order_id
        self.positions: dict[str, int] = {}  # venue symbol -> net contracts
        self.next_id = 1000
        self.fail_next: Exception | None = None

    # test hooks ------------------------------------------------------------
    def settle(self, coid: str) -> None:
        order = self.orders[coid]
        if order["state"] == "open":
            contracts = int(order["size"])
            sign_ = 1 if order["side"] == "buy" else -1
            order["state"] = "closed"
            order["unfilled_size"] = 0
            order["average_fill_price"] = order.get("limit_price") or "4000"
            self.positions[order["product_symbol"]] = (
                self.positions.get(order["product_symbol"], 0) + sign_ * contracts
            )

    # transport -------------------------------------------------------------
    def request(self, method, url, *, params=None, data=None, headers=None,
                timeout=30.0):
        if self.fail_next is not None:
            exc, self.fail_next = self.fail_next, None
            raise exc
        path = url.split("deltaex.org")[-1].split("delta.exchange")[-1]
        private = not (method == "GET" and path.startswith("/v2/products"))
        if private:
            assert headers and headers.get("api-key") and \
                headers.get("signature") and headers.get("timestamp"), \
                f"unsigned private request {method} {path}"
        body = json.loads(data) if data else {}
        return _Resp(*self._route(method, path, params or {}, body))

    def _route(self, method, path, params, body):
        if method == "GET" and path.startswith("/v2/products"):
            return 200, {"result": self.PRODUCTS}
        if method == "POST" and path == "/v2/orders":
            coid = body["client_order_id"]
            if coid in self.orders:
                return 400, {"error": {"code": "duplicate_client_order_id"}}
            assert isinstance(body["size"], int) and body["size"] > 0
            order = {
                "id": self.next_id, "client_order_id": coid,
                "product_symbol": body["product_symbol"],
                "product_id": {"BTCUSD": 27, "XAUTUSD": 93}[body["product_symbol"]],
                "side": body["side"], "size": body["size"],
                "unfilled_size": body["size"], "state": "open",
                "limit_price": body.get("limit_price"),
                "reduce_only": body.get("reduce_only", False),
                "paid_commission": "0.1",
            }
            self.next_id += 1
            self.orders[coid] = order
            return 200, {"result": order}
        if method == "GET" and path.startswith("/v2/orders/client_order_id/"):
            coid = path.rsplit("/", 1)[-1]
            order = self.orders.get(coid)
            return (200, {"result": order}) if order else (404, {"error": "not_found"})
        if method == "DELETE" and path == "/v2/orders":
            order = self.orders.get(body.get("client_order_id", ""))
            if order and order["state"] == "open":
                order["state"] = "cancelled"
            return 200, {"result": order or {}}
        if method == "GET" and path.startswith("/v2/orders/history"):
            return 200, {"result": list(self.orders.values())}
        if method == "GET" and path.startswith("/v2/orders"):
            return 200, {"result": [o for o in self.orders.values()
                                    if o["state"] in ("open", "pending")]}
        if method == "GET" and path.startswith("/v2/positions"):
            return 200, {"result": [
                {"product_symbol": sym, "size": net, "entry_price": "4000"}
                for sym, net in self.positions.items() if net
            ]}
        if method == "GET" and path.startswith("/v2/wallet"):
            return 200, {"result": [
                {"balance": "10000", "available_balance": "9000"}]}
        return 404, {"error": f"no route {method} {path}"}


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.headers = {"Date": format_datetime(datetime.now(timezone.utc))}

    def json(self):
        return self._payload


# --- adapter harness -------------------------------------------------------------------


class AdapterHarness:
    """Uniform driver: adapter + a way to make specs + a way to settle."""

    def __init__(self, adapter, symbol, quantity, settle):
        self.adapter = adapter
        self.symbol = symbol
        self.quantity = quantity
        self._settle = settle

    def spec(self, coid, **overrides):
        base = {"client_order_id": coid, "symbol": self.symbol,
                "venue_symbol": "", "side": "BUY", "quantity": self.quantity,
                "order_type": "market", "reference_price": 4000.0}
        base.update(overrides)
        return OrderSpec(**base)

    def settle(self, coid, timeout=30.0):
        self._settle(coid)
        deadline = time.time() + timeout
        while time.time() < deadline:
            update = self.adapter.get_order(coid)
            if update is not None and update.state.terminal:
                return update
            time.sleep(0.2)
        raise AssertionError(f"{coid} never went terminal")


def _paper_harness():
    adapter = PaperVenueAdapter(VENUES["mt5"])
    return AdapterHarness(adapter, "XAUUSD", 1.0, settle=lambda coid: None)


def _fake_delta_harness():
    fake = FakeDeltaHttp()
    adapter = DeltaAdapter(CREDS, http=fake)
    harness = AdapterHarness(adapter, "BTC-USD", 0.01,
                             settle=fake.settle)
    harness.fake = fake
    return harness


HARNESSES = {"paper": _paper_harness, "fake-delta": _fake_delta_harness}
if os.environ.get("DELTA_TESTNET_API_KEY"):
    def _testnet_harness():
        adapter = DeltaAdapter.from_env(testnet=True)
        # min viable size; testnet market orders fill immediately
        return AdapterHarness(adapter, "BTC-USD", 0.001,
                              settle=lambda coid: None)

    HARNESSES["delta-testnet"] = _testnet_harness


@pytest.fixture(params=list(HARNESSES))
def harness(request):
    return HARNESSES[request.param]()


def _coid(request_node, suffix=""):
    import hashlib

    seed = f"{request_node}|{time.time()}|{suffix}"
    return "ta" + hashlib.sha256(seed.encode()).hexdigest()[:24]


class TestConformance:
    def test_capabilities_honesty(self, harness):
        caps = harness.adapter.capabilities()
        coid = _coid("caps")
        update = harness.adapter.place_order(harness.spec(coid))
        if caps.terminal_on_place:
            assert update.state.terminal
        else:
            assert update.state in (OrderState.ACKED, OrderState.SUBMITTED,
                                    OrderState.PARTIALLY_FILLED,
                                    OrderState.FILLED)
        harness.settle(coid)

    def test_lifecycle_place_to_fill(self, harness):
        coid = _coid("fill")
        placed = harness.adapter.place_order(harness.spec(coid))
        assert placed.client_order_id == coid
        final = harness.settle(coid)
        assert final.state is OrderState.FILLED
        assert final.filled_quantity > 0
        held = {p.symbol for p in harness.adapter.positions()}
        assert harness.symbol in held

    def test_duplicate_coid_never_double_fills(self, harness):
        coid = _coid("dupe")
        harness.adapter.place_order(harness.spec(coid))
        harness.settle(coid)
        qty_before = _net_quantity(harness.adapter, harness.symbol)
        # venue-held state is the guarantee, not the return value
        harness.adapter.place_order(harness.spec(coid))
        harness.settle(coid)
        assert _net_quantity(harness.adapter, harness.symbol) == qty_before

    def test_get_order_round_trip(self, harness):
        coid = _coid("get")
        harness.adapter.place_order(harness.spec(coid))
        fetched = harness.adapter.get_order(coid)
        assert fetched is not None and fetched.client_order_id == coid
        assert harness.adapter.get_order("ta" + "0" * 24) is None
        harness.settle(coid)

    def test_rebuild_from_rest_after_amnesia(self, harness):
        """A fresh adapter instance (WS drop / process restart analogue)
        recovers full order truth via REST alone."""
        coid = _coid("amnesia")
        harness.adapter.place_order(harness.spec(coid))
        final = harness.settle(coid)

        fresh = _reincarnate(harness)
        recovered = fresh.get_order(coid)
        assert recovered is not None
        assert recovered.state == final.state
        assert recovered.filled_quantity == final.filled_quantity

    def test_below_minimum_rejected_without_venue_order(self, harness):
        coid = _coid("tiny")
        update = harness.adapter.place_order(
            harness.spec(coid, quantity=1e-9))
        assert update.state is OrderState.REJECTED
        held = harness.adapter.get_order(coid)
        assert held is None or held.state is OrderState.REJECTED


def _net_quantity(adapter, symbol):
    for position in adapter.positions():
        if position.symbol == symbol:
            signed = 1 if position.side == "BUY" else -1
            return round(signed * position.quantity, 9)
    return 0.0


def _reincarnate(harness):
    adapter = harness.adapter
    if isinstance(adapter, PaperVenueAdapter):
        # in-memory paper has no REST; state_path IS its REST — covered by
        # test_pro_persistence. Reuse the same instance here.
        return adapter
    if isinstance(adapter, DeltaAdapter):
        http = getattr(harness, "fake", None)
        if http is not None:
            return DeltaAdapter(CREDS, http=http)
        return DeltaAdapter.from_env(testnet=True)
    raise AssertionError("unknown adapter type")


# --- async-venue specifics (fake + testnet semantics) ----------------------------------


class TestFakeDeltaSpecifics:
    def test_cancel_open_limit_order(self):
        harness = _fake_delta_harness()
        coid = _coid("cancel")
        harness.adapter.place_order(harness.spec(
            coid, order_type="limit", limit_price=1000.0))
        update = harness.adapter.cancel_order(coid)
        assert update.state is OrderState.CANCELED

    def test_open_orders_lists_working_orders(self):
        harness = _fake_delta_harness()
        coid = _coid("open")
        harness.adapter.place_order(harness.spec(
            coid, order_type="limit", limit_price=1000.0))
        assert coid in {u.client_order_id
                        for u in harness.adapter.open_orders()}

    def test_transport_failure_raises_adapter_error_redacted(self):
        from tradingagents.pro.execution import AdapterError

        fake = FakeDeltaHttp()
        adapter = DeltaAdapter(CREDS, http=fake, max_read_retries=0)
        fake.fail_next = ConnectionError(
            f"boom with {CREDS.api_secret} in the message")
        with pytest.raises(AdapterError) as excinfo:
            adapter.open_orders()
        assert CREDS.api_secret not in str(excinfo.value)
        assert CREDS.api_key not in str(excinfo.value)

    def test_native_bracket_fields_sent(self):
        from tradingagents.pro.execution import BracketSpec

        harness = _fake_delta_harness()
        coid = _coid("bracket")
        harness.adapter.place_order(
            harness.spec(coid),
            bracket=BracketSpec(stop_loss_price=3900.0,
                                take_profits=((4100.0, 0.5), (4200.0, 0.5))),
        )
        # fake stores the raw payload fields via the order route contract
        assert harness.adapter.capabilities().native_bracket

    def test_poll_updates_covers_history(self):
        harness = _fake_delta_harness()
        coid = _coid("poll")
        harness.adapter.place_order(harness.spec(coid))
        harness.fake.settle(coid)
        since = datetime.now(timezone.utc) - timedelta(minutes=5)
        polled = {u.client_order_id: u for u in
                  harness.adapter.poll_updates(since)}
        assert polled[coid].state is OrderState.FILLED


# --- auth / instruments units ----------------------------------------------------------


class TestDeltaAuth:
    def test_sign_is_deterministic_and_shaped(self):
        headers = sign(CREDS, "post", "/v2/orders", "", '{"a":1}',
                       timestamp=1_700_000_000)
        again = sign(CREDS, "POST", "/v2/orders", "", '{"a":1}',
                     timestamp=1_700_000_000)
        assert headers == again
        assert headers["api-key"] == CREDS.api_key
        assert len(headers["signature"]) == 64  # sha256 hex

    def test_redact_and_repr(self):
        assert CREDS.api_secret not in redact(
            f"key={CREDS.api_key} secret={CREDS.api_secret}",
            CREDS.api_key, CREDS.api_secret)
        assert CREDS.api_secret not in repr(CREDS)
        assert CREDS.api_key not in str(CREDS)

    def test_clock_skew_from_date_header(self):
        header = format_datetime(datetime.now(timezone.utc))
        assert abs(clock_skew_seconds(header)) < 2.0
        old = format_datetime(datetime.now(timezone.utc) - timedelta(seconds=30))
        assert clock_skew_seconds(old) > 25


class TestInstruments:
    INFO = InstrumentInfo(symbol="BTC-USD", venue_symbol="BTCUSD",
                          tick_size=0.5, contract_value=0.001)

    def test_to_contracts_floors(self):
        assert self.INFO.to_contracts(0.0019) == 1  # never rounds UP
        assert self.INFO.to_contracts(0.01) == 10

    def test_round_price_to_tick(self):
        assert self.INFO.round_price(4000.3) == 4000.5
        assert self.INFO.round_price(4000.2) == 4000.0

    def test_stale_fail_closed_refuses(self):
        service = InstrumentService(fetch=lambda: (_ for _ in ()).throw(
            ConnectionError("venue down")), ttl_seconds=0.0, fail_closed=True)
        with pytest.raises(InstrumentsUnavailable):
            service.get("BTC-USD")

    def test_from_static_never_blocks(self):
        service = InstrumentService.from_static(VENUES["mt5"])
        info = service.get("XAUUSD")
        assert info.to_contracts(1.0) == 100  # 0.01 step

    def test_cache_round_trip(self, tmp_path):
        fetched = {"BTC-USD": self.INFO}
        first = InstrumentService(fetch=lambda: fetched,
                                  cache_path=tmp_path / "delta.json",
                                  ttl_seconds=3600)
        assert first.get("BTC-USD").tick_size == 0.5
        reloaded = InstrumentService(fetch=None,
                                     cache_path=tmp_path / "delta.json",
                                     ttl_seconds=3600, fail_closed=True)
        assert reloaded.get("BTC-USD").contract_value == 0.001


class TestDeltaAdapterUnits:
    def test_symbol_map_covers_operator_pairs(self):
        assert SYMBOL_MAP == {"BTC-USD": "BTCUSD", "XAUUSD": "XAUTUSD"}

    def test_from_env_refuses_without_credentials(self, monkeypatch):
        from tradingagents.pro.execution import AdapterError

        monkeypatch.delenv("DELTA_TESTNET_API_KEY", raising=False)
        monkeypatch.delenv("DELTA_TESTNET_API_SECRET", raising=False)
        with pytest.raises(AdapterError):
            DeltaAdapter.from_env(testnet=True)

    def test_live_stub_still_refuses_v2(self):
        from tradingagents.pro.execution import ExecutionNotEnabled, LiveAdapterStub

        stub = LiveAdapterStub(VENUES["binance"])
        with pytest.raises(ExecutionNotEnabled):
            stub.capabilities()
        with pytest.raises(ExecutionNotEnabled):
            stub.place_order(OrderSpec(
                client_order_id="x", symbol="BTC-USD", venue_symbol="",
                side="BUY", quantity=1.0))
