from __future__ import annotations

import asyncio
import logging
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from tradingagents_service.artifacts import ArtifactStore
from tradingagents_service.runner import run_shadow_job

from .types import JobEventSink, JobRepository

logger = logging.getLogger(__name__)


async def _safe_emit(
    *,
    event_sink: JobEventSink,
    job_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    try:
        await event_sink.emit(job_id=job_id, event_type=event_type, payload=payload)
    except Exception:  # noqa: BLE001
        # Event delivery must not disrupt run state transitions.
        return


async def run_worker_loop(
    *,
    repository: JobRepository,
    event_sink: JobEventSink,
    worker_id: str,
    artifact_store: ArtifactStore | None = None,
    poll_interval_seconds: float = 1.0,
    stop_event: asyncio.Event | None = None,
) -> None:
    local_stop = stop_event or asyncio.Event()
    while not local_stop.is_set():
        try:
            job = await repository.claim_next(worker_id=worker_id)
        except Exception:  # noqa: BLE001
            logger.exception("worker claim failed; retrying")
            try:
                await asyncio.wait_for(local_stop.wait(), timeout=poll_interval_seconds)
            except asyncio.TimeoutError:
                pass
            continue
        if job is None:
            try:
                await asyncio.wait_for(local_stop.wait(), timeout=poll_interval_seconds)
            except asyncio.TimeoutError:
                pass
            continue

        await repository.mark_running(job_id=job.job_id, worker_id=worker_id)
        await _safe_emit(event_sink=event_sink, job_id=job.job_id, event_type="running", payload={"worker_id": worker_id})
        try:
            def _emit_runtime_progress(payload: dict[str, Any]) -> None:
                event_payload = {"worker_id": worker_id, **payload}
                try:
                    asyncio.run(
                        _safe_emit(
                            event_sink=event_sink,
                            job_id=job.job_id,
                            event_type="stage_progress",
                            payload=event_payload,
                        )
                    )
                except Exception:  # noqa: BLE001
                    return

            result = await asyncio.to_thread(
                run_shadow_job,
                job.request,
                artifact_store,
                progress_callback=_emit_runtime_progress,
            )
            stored = await repository.mark_succeeded(job_id=job.job_id, result=result)
            if stored is not False:
                await _safe_emit(
                    event_sink=event_sink,
                    job_id=job.job_id,
                    event_type="succeeded",
                    payload={"result": asdict(result)},
                )
        except Exception as exc:  # noqa: BLE001
            await repository.mark_failed(job_id=job.job_id, error_message=str(exc))
            await _safe_emit(
                event_sink=event_sink,
                job_id=job.job_id,
                event_type="failed",
                payload={"error": str(exc), "traceback": traceback.format_exc()},
            )

    await _safe_emit(
        event_sink=event_sink,
        job_id="*",
        event_type="worker_stopped",
        payload={"worker_id": worker_id, "timestamp": datetime.now(timezone.utc).isoformat()},
    )
