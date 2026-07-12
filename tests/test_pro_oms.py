"""Go-live Phase 2: OMS state machine, WAL, crash recovery, brackets.

Chaos discipline: every crash point between "journal" and "venue response"
is simulated by building the journal state that crash would leave behind,
then running ``recover()`` with a fresh OrderManager — exactly what a
restarted process does. The invariant under test is always the same:
a correct, non-duplicated book.
"""

from __future__ import annotations

import time

import pytest

from tests.test_pro_execution_conformance import CREDS, FakeDeltaHttp
from tradingagents.pro.execution import (
    VENUES,
    BracketSpec,
    BracketWatchdog,
    ExecutionPlan,
    IllegalTransition,
    ManagedOrder,
    OrderJournal,
    OrderManager,
    OrderSpec,
    OrderState,
    OrderUpdate,
    PaperVenueAdapter,
    RecoveryFailed,
    ids,
)
from tradingagents.pro.execution.adapters.delta import DeltaAdapter


def _plan(**overrides) -> ExecutionPlan:
    base = {
        "run_id": "run-1", "decision_hash": "d" * 64, "symbol": "BTC-USD",
        "side": "BUY", "quantity": 0.01, "reference_price": 4000.0,
        "bracket": BracketSpec(stop_loss_price=3900.0,
                               take_profits=((4200.0, 1.0),)),
        "protection_mode": "venue_bracket",
    }
    base.update(overrides)
    return ExecutionPlan(**base)


def _delta_oms(tmp_path, fake=None, **kwargs) -> tuple[OrderManager, FakeDeltaHttp]:
    fake = fake or FakeDeltaHttp()
    adapter = DeltaAdapter(CREDS, http=fake, max_read_retries=0)
    adapter.instruments.refresh()  # warm cache so fault injection hits orders
    oms = OrderManager(adapter, journal_path=tmp_path / "journal.jsonl",
                       **kwargs)
    oms.recover()
    return oms, fake


class _NoBracketDelta(DeltaAdapter):
    """Async venue WITHOUT native brackets — forces the synthetic path."""

    def capabilities(self):
        caps = super().capabilities()
        from dataclasses import replace

        return replace(caps, native_bracket=False)


class TestIds:
    def test_deterministic_and_shaped(self):
        a = ids.client_order_id("run", "hash", ids.ENTRY)
        b = ids.client_order_id("run", "hash", ids.ENTRY)
        assert a == b and a.startswith("ta") and len(a) == 26
        assert ids.client_order_id("run", "hash", ids.STOP) != a


class TestTransitionTable:
    def test_legal_chain(self):
        order = ManagedOrder(spec=OrderSpec(
            client_order_id="ta" + "0" * 24, symbol="BTC-USD",
            venue_symbol="", side="BUY", quantity=1.0))
        for state in (OrderState.SUBMITTED, OrderState.ACKED,
                      OrderState.PARTIALLY_FILLED, OrderState.FILLED):
            order.apply(OrderUpdate(client_order_id=order.client_order_id,
                                    state=state, filled_quantity=0.5))
        assert order.state is OrderState.FILLED

    def test_terminal_never_transitions(self):
        order = ManagedOrder(spec=OrderSpec(
            client_order_id="ta" + "1" * 24, symbol="BTC-USD",
            venue_symbol="", side="BUY", quantity=1.0))
        order.apply(OrderUpdate(client_order_id=order.client_order_id,
                                state=OrderState.REJECTED))
        with pytest.raises(IllegalTransition):
            order.apply(OrderUpdate(client_order_id=order.client_order_id,
                                    state=OrderState.FILLED))


class TestExecuteHappyPath:
    def test_native_bracket_single_call(self, tmp_path):
        oms, fake = _delta_oms(tmp_path)
        order = oms.execute(_plan())
        assert order.state is OrderState.ACKED  # async venue
        coid = order.client_order_id
        assert fake.orders[coid]["state"] == "open"
        # same decision resubmitted -> same ManagedOrder, one venue order
        again = oms.execute(_plan())
        assert again is order and len(fake.orders) == 1

    def test_paper_terminal_on_place(self, tmp_path):
        adapter = PaperVenueAdapter(VENUES["mt5"])
        oms = OrderManager(adapter, journal_path=tmp_path / "j.jsonl")
        oms.recover()
        order = oms.execute(_plan(symbol="XAUUSD", quantity=1.0,
                                  protection_mode="bar_close"))
        assert order.state is OrderState.FILLED


class TestResolveLoop:
    def test_transport_failure_then_resubmit_no_duplicate(self, tmp_path):
        fake = FakeDeltaHttp()
        oms, _ = _delta_oms(tmp_path, fake=fake)
        fake.fail_next = ConnectionError("wire cut before send")
        order = oms.execute(_plan())
        # resolve: not on venue -> resent with the SAME coid; exactly one order
        assert order.state is OrderState.ACKED
        assert len(fake.orders) == 1

    def test_unresolvable_is_rejected_never_guessed(self, tmp_path):
        fake = FakeDeltaHttp()
        adapter = DeltaAdapter(CREDS, http=fake, max_read_retries=0)
        adapter.instruments.refresh()
        oms = OrderManager(adapter, journal_path=tmp_path / "j.jsonl",
                           max_resolve_retries=1)
        oms.recover()

        class _AlwaysDown:
            def request(self, *a, **k):
                raise ConnectionError("venue dark")

        adapter._http = _AlwaysDown()
        order = oms.execute(_plan())
        assert order.state is OrderState.REJECTED
        assert "unresolvable" in order.reason


class TestCrashRecovery:
    """The three chaos points from the acceptance criteria."""

    def _journal(self, tmp_path):
        return OrderJournal(tmp_path / "journal.jsonl")

    def _spec(self, coid):
        return OrderSpec(client_order_id=coid, symbol="BTC-USD",
                         venue_symbol="", side="BUY", quantity=0.01,
                         reference_price=4000.0)

    def test_crash_between_intent_and_send(self, tmp_path):
        coid = ids.client_order_id("run-1", "d" * 64, ids.ENTRY)
        journal = self._journal(tmp_path)
        journal.intent(ManagedOrder(spec=self._spec(coid), leg=ids.ENTRY))
        journal.close()  # process dies before "submitting"

        oms, fake = _delta_oms(tmp_path)
        order = oms.orders[coid]
        assert order.state is OrderState.ABANDONED  # never auto-resent
        assert fake.orders == {}                    # nothing on the venue

    def test_crash_between_send_and_ack_order_landed(self, tmp_path):
        # the send reached the venue but the response never came back
        fake = FakeDeltaHttp()
        adapter = DeltaAdapter(CREDS, http=fake, max_read_retries=0)
        coid = ids.client_order_id("run-1", "d" * 64, ids.ENTRY)
        adapter.place_order(self._spec(coid))     # venue knows the order

        journal = self._journal(tmp_path)
        order = ManagedOrder(spec=self._spec(coid), leg=ids.ENTRY)
        journal.intent(order)
        journal.submitting(coid)
        journal.close()                            # crash before response

        oms, _ = _delta_oms(tmp_path, fake=fake)
        recovered = oms.orders[coid]
        assert recovered.state is OrderState.ACKED  # adopted venue truth
        assert len(fake.orders) == 1                # no duplicate

    def test_crash_between_send_and_ack_order_never_landed(self, tmp_path):
        coid = ids.client_order_id("run-1", "d" * 64, ids.ENTRY)
        journal = self._journal(tmp_path)
        order = ManagedOrder(spec=self._spec(coid), leg=ids.ENTRY)
        journal.intent(order)
        journal.submitting(coid)
        journal.close()

        oms, fake = _delta_oms(tmp_path)
        assert oms.orders[coid].state is OrderState.REJECTED
        assert "not found on venue" in oms.orders[coid].reason
        assert fake.orders == {}

    def test_crash_mid_partial_fill(self, tmp_path):
        fake = FakeDeltaHttp()
        adapter = DeltaAdapter(CREDS, http=fake, max_read_retries=0)
        coid = ids.client_order_id("run-1", "d" * 64, ids.ENTRY)
        adapter.place_order(self._spec(coid))
        fake.settle(coid)                          # fills while we're dead

        journal = self._journal(tmp_path)
        order = ManagedOrder(spec=self._spec(coid), leg=ids.ENTRY)
        journal.intent(order)
        journal.submitting(coid)
        order.state = OrderState.PARTIALLY_FILLED
        journal.transition(order, OrderState.PENDING_SUBMIT)
        journal.close()

        oms, _ = _delta_oms(tmp_path, fake=fake)
        recovered = oms.orders[coid]
        assert recovered.state is OrderState.FILLED
        assert recovered.filled_quantity > 0
        assert len(fake.orders) == 1

    def test_venue_unreachable_blocks_boot(self, tmp_path):
        coid = ids.client_order_id("run-1", "d" * 64, ids.ENTRY)
        journal = self._journal(tmp_path)
        order = ManagedOrder(spec=self._spec(coid), leg=ids.ENTRY)
        journal.intent(order)
        journal.submitting(coid)
        journal.close()

        class _Dark:
            def request(self, *a, **k):
                raise ConnectionError("venue dark")

        adapter = DeltaAdapter(CREDS, http=_Dark(), max_read_retries=0)
        oms = OrderManager(adapter, journal_path=tmp_path / "journal.jsonl")
        with pytest.raises(RecoveryFailed):
            oms.recover(max_attempts=2)
        assert oms.recovered is False


class TestSyntheticBracketAndWatchdog:
    def _oms(self, tmp_path, **kwargs):
        fake = FakeDeltaHttp()
        adapter = _NoBracketDelta(CREDS, http=fake, max_read_retries=0)
        adapter.instruments.refresh()
        oms = OrderManager(adapter, journal_path=tmp_path / "j.jsonl",
                           **kwargs)
        oms.recover()
        return oms, fake

    def test_protection_placed_after_entry_fill(self, tmp_path):
        oms, fake = self._oms(tmp_path)
        entry = oms.execute(_plan())
        assert entry.client_order_id in oms.pending_protection
        fake.settle(entry.client_order_id)
        watchdog = BracketWatchdog(oms)
        watchdog.tick(time.time())
        # entry filled -> stop + final TP must exist and pending cleared
        legs = {o.leg for o in oms.orders.values()}
        assert legs >= {ids.ENTRY, ids.STOP, ids.take_profit_leg(0)}
        assert oms.pending_protection == {}
        assert oms.has_venue_protection("BTC-USD")

    def test_watchdog_flattens_when_stop_cannot_be_placed(self, tmp_path):
        class _StopRejecting(FakeDeltaHttp):
            def _route(self, method, path, params, body):
                if (method == "POST" and path == "/v2/orders"
                        and body.get("reduce_only")
                        and body.get("limit_price") == "3900.0"):
                    return 400, {"error": "stop placement refused"}
                return super()._route(method, path, params, body)

        fake = _StopRejecting()
        adapter = _NoBracketDelta(CREDS, http=fake, max_read_retries=0)
        adapter.instruments.refresh()
        from tradingagents.pro.execution import AuditLog

        audit = AuditLog()
        oms = OrderManager(adapter, journal_path=tmp_path / "j.jsonl",
                           audit=audit, protection_deadline_seconds=0.0)
        oms.recover()
        entry = oms.execute(_plan())
        fake.settle(entry.client_order_id)
        watchdog = BracketWatchdog(oms)
        watchdog.tick(time.time() + 1.0)  # past the deadline

        events = [e["event"] for e in audit.entries]
        assert "watchdog_flattened" in events
        # async venue: the flatten order is working; once it fills, flat
        flatten = next(o for o in oms.orders.values() if o.leg == ids.FLATTEN)
        fake.settle(flatten.client_order_id)
        oms.poll()
        assert fake.positions.get("BTCUSD", 0) == 0
        # no orphaned protections keep working after the flatten
        working = [o for o in oms.orders.values()
                   if o.sent and not o.state.terminal
                   and o.leg != ids.FLATTEN]
        assert working == []
        assert audit.verify()

    def test_oco_stop_fill_cancels_tp(self, tmp_path):
        oms, fake = self._oms(tmp_path)
        entry = oms.execute(_plan())
        fake.settle(entry.client_order_id)
        watchdog = BracketWatchdog(oms)
        watchdog.tick(time.time())
        stop_coid = ids.client_order_id("run-1", "d" * 64, ids.STOP)
        tp_coid = ids.client_order_id("run-1", "d" * 64,
                                      ids.take_profit_leg(0))
        fake.settle(stop_coid)                     # stop fires on the venue
        watchdog.tick(time.time())
        assert oms.orders[stop_coid].state is OrderState.FILLED
        assert oms.orders[tp_coid].state is OrderState.CANCELED
        closed = oms.drain_closed()
        assert len(closed) == 1 and closed[0].reason == "stop_loss"


class TestRouterViaOms:
    def test_run_once_with_oms_matches_legacy_behavior(self, tmp_path):
        from tests.test_pro_persistence import _build_service

        service = _build_service(tmp_path, closes=[4000.0])
        oms = OrderManager(service.router.adapter,
                           journal_path=tmp_path / "oms.jsonl",
                           audit=service.router.audit)
        oms.recover()
        service.router.oms = oms
        summary = service.run_once()
        assert summary["order_status"] == "filled"
        assert list(service.open_positions) == ["XAUUSD"]
        events = [e["event"] for e in service.router.audit.entries]
        assert "order_received" in events and "order_result" in events
        assert service.router.audit.verify()
        report = service.router.reconcile()
        assert report.in_sync

    def test_unrecovered_oms_refuses(self, tmp_path):
        from tests.test_pro_persistence import _build_service

        service = _build_service(tmp_path, closes=[4000.0])
        service.router.oms = OrderManager(
            service.router.adapter, journal_path=tmp_path / "oms.jsonl")
        summary = service.run_once()
        assert summary["order_status"] == "rejected"
        events = [e["event"] for e in service.router.audit.entries]
        assert "oms_not_recovered" in events
