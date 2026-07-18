"""Atomic disk-replay to live-event handoff for localhost SSE clients."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from dataclasses import dataclass
from typing import Final

from tradingagents.observability.events import PersistedEvent, RunEventDraft

from .store import RunStore

DEFAULT_SUBSCRIBER_CAPACITY: Final = 512
DEFAULT_KEEPALIVE_SECONDS: Final = 15.0


@dataclass(frozen=True)
class Keepalive:
    """An in-memory SSE comment boundary; it is never persisted."""

    comment: str = "keepalive"


class SubscriptionClosed(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"event subscription closed: {reason}")


class EventSubscription:
    """One event-loop-owned replay/live stream."""

    def __init__(
        self,
        broker: EventBroker,
        run_id: str,
        *,
        loop: asyncio.AbstractEventLoop,
        replay: tuple[PersistedEvent, ...],
        watermark: int,
        after: int,
        capacity: int,
        keepalive_seconds: float,
        close_after_replay: bool,
    ) -> None:
        self.broker = broker
        self.run_id = run_id
        self.loop = loop
        self.replay = deque(replay)
        self.watermark = watermark
        self.after = after
        self.capacity = capacity
        self.keepalive_seconds = keepalive_seconds
        self.close_after_replay = close_after_replay
        self.queue: deque[PersistedEvent] = deque()
        self.condition = asyncio.Condition()
        self.closed_reason: str | None = None
        self._last_live_sequence = watermark
        self._registered = True

    @property
    def pending_count(self) -> int:
        return len(self.replay) + len(self.queue)

    async def receive(
        self,
        *,
        keepalive_timeout: float | None = None,
    ) -> PersistedEvent | None:
        item = await self.next_event(timeout=keepalive_timeout)
        return None if isinstance(item, Keepalive) else item

    async def wait_closed(self) -> str:
        async with self.condition:
            await self.condition.wait_for(lambda: self.closed_reason is not None)
            assert self.closed_reason is not None
            return self.closed_reason

    async def next_event(
        self,
        *,
        timeout: float | None = None,
    ) -> PersistedEvent | Keepalive:
        if self.replay:
            return self.replay.popleft()
        if self.close_after_replay and self.closed_reason is None:
            await self.close("terminal")
        if self.close_after_replay:
            self.queue.clear()
            raise SubscriptionClosed(self.closed_reason or "terminal")
        wait_seconds = self.keepalive_seconds if timeout is None else timeout
        async with self.condition:
            if not self.queue and self.closed_reason is None:
                try:
                    await asyncio.wait_for(
                        self.condition.wait_for(
                            lambda: bool(self.queue) or self.closed_reason is not None
                        ),
                        timeout=wait_seconds,
                    )
                except TimeoutError:
                    return Keepalive()
            if self.queue:
                return self.queue.popleft()
            raise SubscriptionClosed(self.closed_reason or "closed")

    async def close(self, reason: str = "client_disconnected") -> None:
        self.broker.unsubscribe(self, reason=reason)
        async with self.condition:
            self.condition.notify_all()

    async def __aenter__(self) -> EventSubscription:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    def __aiter__(self) -> EventSubscription:
        return self

    async def __anext__(self) -> PersistedEvent | Keepalive:
        try:
            return await self.next_event()
        except SubscriptionClosed as exc:
            if exc.reason == "terminal":
                raise StopAsyncIteration from exc
            raise

    def _enqueue_on_loop(self, event: PersistedEvent) -> None:
        if self.closed_reason is not None or event.sequence <= self._last_live_sequence:
            return
        if len(self.queue) >= self.capacity:
            self.queue.clear()
            self.closed_reason = "slow_consumer"
            self.broker._discard(self)
        else:
            self.queue.append(event)
            self._last_live_sequence = event.sequence
        self._wake_waiters()

    def _close_on_loop(self, reason: str) -> None:
        if self.closed_reason is None:
            self.closed_reason = reason
        self._wake_waiters()

    def _wake_waiters(self) -> None:
        async def notify() -> None:
            async with self.condition:
                self.condition.notify_all()

        if not self.loop.is_closed():
            self.loop.create_task(notify())


class EventBroker:
    """Persist events and publish them under the same per-run lock."""

    def __init__(
        self,
        store: RunStore,
        *,
        subscriber_capacity: int = DEFAULT_SUBSCRIBER_CAPACITY,
        keepalive_seconds: float = DEFAULT_KEEPALIVE_SECONDS,
    ) -> None:
        if subscriber_capacity < 1:
            raise ValueError("subscriber_capacity must be positive")
        if keepalive_seconds <= 0:
            raise ValueError("keepalive_seconds must be positive")
        self.store = store
        self.subscriber_capacity = subscriber_capacity
        self.keepalive_seconds = keepalive_seconds
        self._subscribers: dict[str, set[EventSubscription]] = {}
        self._registry_guard = threading.Lock()

    def persist(self, draft: RunEventDraft) -> PersistedEvent:
        """Append/fsync first, then schedule live delivery before releasing the lock."""
        with self.store.lock_for(draft.run_id):
            event = self.store.append_event(draft)
            for subscription in self._run_subscribers(draft.run_id):
                try:
                    subscription.loop.call_soon_threadsafe(
                        subscription._enqueue_on_loop,
                        event,
                    )
                except RuntimeError:
                    self._discard(subscription)
            return event

    def publish(self, draft: RunEventDraft) -> PersistedEvent:
        """Public event-sink alias used by observers and background workers."""
        return self.persist(draft)

    async def subscribe(
        self,
        run_id: str,
        *,
        after: int = 0,
        close_after_replay: bool = False,
        capacity: int | None = None,
    ) -> EventSubscription:
        if after < 0:
            raise ValueError("after must be non-negative")
        selected_capacity = self.subscriber_capacity if capacity is None else capacity
        if selected_capacity < 1:
            raise ValueError("capacity must be positive")
        loop = asyncio.get_running_loop()
        with self.store.lock_for(run_id):
            events = self.store.read_events(run_id)
            watermark = events[-1].sequence if events else 0
            subscription = EventSubscription(
                self,
                run_id,
                loop=loop,
                replay=tuple(
                    event
                    for event in events
                    if after < event.sequence <= watermark
                ),
                watermark=watermark,
                after=after,
                capacity=selected_capacity,
                keepalive_seconds=self.keepalive_seconds,
                close_after_replay=close_after_replay,
            )
            with self._registry_guard:
                self._subscribers.setdefault(run_id, set()).add(subscription)
            return subscription

    def unsubscribe(
        self,
        subscription: EventSubscription,
        *,
        reason: str = "client_disconnected",
    ) -> None:
        if not reason:
            raise ValueError("unsubscribe reason is required")
        with self.store.lock_for(subscription.run_id):
            self._discard(subscription)
            if subscription.loop.is_closed():
                subscription.closed_reason = subscription.closed_reason or reason
                return
            if self._on_loop(subscription):
                subscription._close_on_loop(reason)
            else:
                try:
                    subscription.loop.call_soon_threadsafe(
                        subscription._close_on_loop,
                        reason,
                    )
                except RuntimeError:
                    subscription.closed_reason = subscription.closed_reason or reason

    def subscriber_count(self, run_id: str) -> int:
        with self._registry_guard:
            return len(self._subscribers.get(run_id, ()))

    def _run_subscribers(self, run_id: str) -> tuple[EventSubscription, ...]:
        with self._registry_guard:
            return tuple(self._subscribers.get(run_id, ()))

    def _discard(self, subscription: EventSubscription) -> None:
        with self._registry_guard:
            subscriptions = self._subscribers.get(subscription.run_id)
            if subscriptions is None:
                subscription._registered = False
                return
            subscriptions.discard(subscription)
            subscription._registered = False
            if not subscriptions:
                self._subscribers.pop(subscription.run_id, None)

    @staticmethod
    def _on_loop(subscription: EventSubscription) -> bool:
        try:
            return asyncio.get_running_loop() is subscription.loop
        except RuntimeError:
            return False
