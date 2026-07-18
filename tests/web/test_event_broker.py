"""Concurrency contracts for the durable replay-to-live event broker."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from tradingagents.observability.events import PersistedEvent, RunEventDraft
from tradingagents.web.broker import EventBroker, Keepalive, SubscriptionClosed
from tradingagents.web.run_models import RunSnapshot, generate_run_id
from tradingagents.web.store import RunStore


def _run(coroutine: Coroutine[Any, Any, None]) -> None:
    asyncio.run(coroutine)


def _store_with_run(tmp_path) -> tuple[RunStore, str]:
    store = RunStore(tmp_path)
    run_id = generate_run_id()
    store.create_run(
        RunSnapshot.create(
            run_id=run_id,
            ticker="AAPL",
            analysis_date="2026-07-18",
            selected_analysts=("market",),
            llm_provider="openai",
            quick_think_llm="quick",
            deep_think_llm="deep",
            configured_keys={"openai": True},
        )
    )
    return store, run_id


def _draft(run_id: str, index: int) -> RunEventDraft:
    return RunEventDraft(run_id, "future.broker_test", {"index": index})


class _PersistGateStore(RunStore):
    """Pause after fsync so the test can inspect pre-publication state."""

    def __init__(self, root) -> None:
        super().__init__(root)
        self.persisted = threading.Event()
        self.release_append = threading.Event()
        self.shared_lock_was_held = False

    def append_event(self, draft: RunEventDraft) -> PersistedEvent:
        lock = self.lock_for(draft.run_id)
        # RunStore.append_event acquires this lock itself. Seeing it held before
        # calling super proves EventBroker spans persistence *and* publication
        # with that same per-run lock.
        self.shared_lock_was_held = bool(lock._is_owned())  # type: ignore[attr-defined]
        event = super().append_event(draft)
        self.persisted.set()
        if not self.release_append.wait(timeout=5):
            raise AssertionError("test did not release the append gate")
        return event


def test_publish_fsyncs_before_delivery_under_the_shared_run_lock(tmp_path):
    async def scenario() -> None:
        store = _PersistGateStore(tmp_path)
        run_id = generate_run_id()
        store.create_run(
            RunSnapshot.create(
                run_id=run_id,
                ticker="AAPL",
                analysis_date="2026-07-18",
                selected_analysts=("market",),
            )
        )
        broker = EventBroker(store)
        subscription = await broker.subscribe(run_id, after=0)
        failures: list[BaseException] = []

        def publish() -> None:
            try:
                broker.persist(_draft(run_id, 1))
            except BaseException as exc:  # pragma: no cover - asserted below
                failures.append(exc)

        thread = threading.Thread(target=publish)
        thread.start()
        assert store.persisted.wait(timeout=5)
        assert store.shared_lock_was_held is True
        assert store.read_events(run_id)[0].sequence == 1
        assert isinstance(await subscription.next_event(timeout=0), Keepalive)

        store.release_append.set()
        await asyncio.to_thread(thread.join, 5)
        assert not thread.is_alive()
        assert failures == []
        assert (await subscription.next_event()).sequence == 1
        await subscription.close()

    _run(scenario())


class _ReplayGateStore(RunStore):
    """Force one publication to contend with replay while replay owns the lock."""

    def __init__(self, root) -> None:
        super().__init__(root)
        self.gate_enabled = False
        self.replay_entered = threading.Event()
        self.publisher_attempted = threading.Event()
        self.replay_had_shared_lock = False

    def read_events(self, run_id: str, *, after: int = 0, through: int | None = None):
        if self.gate_enabled:
            self.replay_had_shared_lock = bool(
                self.lock_for(run_id)._is_owned()  # type: ignore[attr-defined]
            )
            self.replay_entered.set()
            if not self.publisher_attempted.wait(timeout=5):
                raise AssertionError("publisher never attempted the replay race")
        return super().read_events(run_id, after=after, through=through)


def test_subscribe_watermark_handoff_has_no_gap_or_duplicate(tmp_path):
    async def scenario() -> None:
        store = _ReplayGateStore(tmp_path)
        run_id = generate_run_id()
        store.create_run(
            RunSnapshot.create(
                run_id=run_id,
                ticker="AAPL",
                analysis_date="2026-07-18",
                selected_analysts=("market",),
            )
        )
        broker = EventBroker(store)
        broker.persist(_draft(run_id, 1))
        failures: list[BaseException] = []

        def publish_during_replay() -> None:
            try:
                assert store.replay_entered.wait(timeout=5)
                store.publisher_attempted.set()
                broker.persist(_draft(run_id, 2))
            except BaseException as exc:  # pragma: no cover - asserted below
                failures.append(exc)

        store.gate_enabled = True
        thread = threading.Thread(target=publish_during_replay)
        thread.start()
        subscription = await broker.subscribe(run_id, after=0)
        await asyncio.to_thread(thread.join, 5)

        assert not thread.is_alive()
        assert failures == []
        assert store.replay_had_shared_lock is True
        assert subscription.watermark == 1
        assert [
            (await subscription.next_event()).sequence,
            (await subscription.next_event()).sequence,
        ] == [1, 2]
        assert isinstance(await subscription.next_event(timeout=0), Keepalive)
        await subscription.close()

    _run(scenario())


def test_after_sequence_filters_replay_then_continues_live(tmp_path):
    async def scenario() -> None:
        store, run_id = _store_with_run(tmp_path)
        broker = EventBroker(store)
        for index in range(1, 4):
            broker.persist(_draft(run_id, index))

        subscription = await broker.subscribe(run_id, after=2)
        assert subscription.watermark == 3
        assert (await subscription.next_event()).sequence == 3

        await asyncio.to_thread(broker.persist, _draft(run_id, 4))
        assert (await subscription.next_event()).sequence == 4
        await subscription.close()

    _run(scenario())


def test_future_after_cursor_does_not_deliver_lower_live_sequences(tmp_path):
    async def scenario() -> None:
        store, run_id = _store_with_run(tmp_path)
        broker = EventBroker(store)
        subscription = await broker.subscribe(run_id, after=3)

        for index in range(1, 4):
            await asyncio.to_thread(broker.persist, _draft(run_id, index))
        assert isinstance(await subscription.next_event(timeout=0), Keepalive)

        await asyncio.to_thread(broker.persist, _draft(run_id, 4))
        assert (await subscription.next_event()).sequence == 4
        await subscription.close()

    _run(scenario())


def test_overflow_closes_only_slow_subscription_and_disk_replay_recovers(tmp_path):
    async def scenario() -> None:
        store, run_id = _store_with_run(tmp_path)
        broker = EventBroker(store, subscriber_capacity=2)
        slow = await broker.subscribe(run_id, after=0)
        healthy = await broker.subscribe(run_id, after=0)

        # The healthy subscriber drains each event. The slow subscriber keeps
        # both slots occupied and deterministically overflows on the third.
        for index in range(1, 4):
            await asyncio.to_thread(broker.persist, _draft(run_id, index))
            assert (await healthy.next_event()).sequence == index
        await slow.wait_closed()

        assert slow.closed_reason == "slow_consumer"
        with pytest.raises(SubscriptionClosed) as closed:
            await slow.next_event()
        assert closed.value.reason == "slow_consumer"
        assert healthy.closed_reason is None
        assert broker.subscriber_count(run_id) == 1

        recovered = await broker.subscribe(run_id, after=0)
        assert [
            (await recovered.next_event()).sequence,
            (await recovered.next_event()).sequence,
            (await recovered.next_event()).sequence,
        ] == [1, 2, 3]
        await healthy.close()
        await recovered.close()

    _run(scenario())


def test_keepalive_timeout_is_ephemeral_and_does_not_touch_disk(tmp_path):
    async def scenario() -> None:
        store, run_id = _store_with_run(tmp_path)
        broker = EventBroker(store)
        subscription = await broker.subscribe(run_id, after=0)

        assert isinstance(await subscription.next_event(timeout=0), Keepalive)
        assert subscription.closed_reason is None
        assert store.read_snapshot(run_id).latest_sequence == 0
        assert store.read_events(run_id) == []
        await subscription.close()

    _run(scenario())


def test_terminal_subscription_closes_after_its_captured_watermark(tmp_path):
    async def scenario() -> None:
        store, run_id = _store_with_run(tmp_path)
        broker = EventBroker(store)
        broker.persist(_draft(run_id, 1))
        subscription = await broker.subscribe(
            run_id,
            after=0,
            close_after_replay=True,
        )

        # Even if a later event is scheduled before replay is drained, a
        # terminal response is a finite snapshot through its watermark.
        await asyncio.to_thread(broker.persist, _draft(run_id, 2))
        assert (await subscription.next_event()).sequence == 1
        with pytest.raises(SubscriptionClosed) as closed:
            await subscription.next_event()

        assert closed.value.reason == "terminal"
        assert subscription.pending_count == 0
        assert broker.subscriber_count(run_id) == 0
        assert [event.sequence for event in store.read_events(run_id)] == [1, 2]

    _run(scenario())


def test_close_unregisters_promptly_without_affecting_the_run(tmp_path):
    async def scenario() -> None:
        store, run_id = _store_with_run(tmp_path)
        broker = EventBroker(store)
        subscription = await broker.subscribe(run_id, after=0)
        assert broker.subscriber_count(run_id) == 1

        await subscription.close()

        assert subscription.closed_reason == "client_disconnected"
        assert broker.subscriber_count(run_id) == 0
        persisted = broker.persist(_draft(run_id, 1))
        assert persisted.sequence == 1
        assert store.read_snapshot(run_id).status == "created"

    _run(scenario())


def test_publish_is_safe_from_multiple_worker_threads(tmp_path):
    async def scenario() -> None:
        store, run_id = _store_with_run(tmp_path)
        broker = EventBroker(store, subscriber_capacity=64)
        subscription = await broker.subscribe(run_id, after=0)

        def publish_all() -> list[PersistedEvent]:
            with ThreadPoolExecutor(max_workers=4) as pool:
                return list(
                    pool.map(
                        lambda index: broker.persist(_draft(run_id, index)),
                        range(16),
                    )
                )

        published = await asyncio.to_thread(publish_all)
        received = [await subscription.next_event() for _ in range(16)]

        assert sorted(event.sequence for event in published) == list(range(1, 17))
        assert [event.sequence for event in received] == list(range(1, 17))
        assert [event.sequence for event in store.read_events(run_id)] == list(
            range(1, 17)
        )
        await subscription.close()

    _run(scenario())
