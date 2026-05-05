from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from tradingagents_service.runner.types import ShadowRunRequest, ShadowRunResult


@dataclass(frozen=True)
class QueuedShadowJob:
    job_id: str
    request: ShadowRunRequest
    metadata: dict[str, Any] = field(default_factory=dict)


class JobRepository(Protocol):
    async def claim_next(self, *, worker_id: str) -> QueuedShadowJob | None:
        ...

    async def mark_running(self, *, job_id: str, worker_id: str) -> None:
        ...

    async def mark_succeeded(self, *, job_id: str, result: ShadowRunResult) -> bool | None:
        ...

    async def mark_failed(self, *, job_id: str, error_message: str) -> None:
        ...


class JobEventSink(Protocol):
    async def emit(self, *, job_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        ...
