from __future__ import annotations

import asyncio
import os
import socket
from dataclasses import dataclass
from uuid import UUID

from tradingagents_service.db.models import ShadowRunStatus
from tradingagents_service.db.repository import ArtifactCreate, ShadowRunRepository
from tradingagents_service.db.session import create_session_factory
from tradingagents_service.evaluations import (
    DEFAULT_RUBRIC_DEFINITION,
    DEFAULT_RUBRIC_NAME,
    DEFAULT_RUBRIC_VERSION,
    build_shadow_run_evaluation_input,
    compute_shadow_run_evaluation,
)
from tradingagents_service.precedents import build_precedent_query_text
from tradingagents_service.runner.types import ShadowRunRequest, ShadowRunResult
from tradingagents_service.worker.loop import run_worker_loop
from tradingagents_service.worker.types import JobEventSink, JobRepository, QueuedShadowJob


@dataclass(frozen=True)
class _DbJobRepository(JobRepository):
    db_url: str | None = None
    stale_running_seconds: int = 1800

    async def claim_next(self, *, worker_id: str) -> QueuedShadowJob | None:
        factory = create_session_factory(self.db_url)
        async with factory() as session:
            repo = ShadowRunRepository(session)
            await repo.requeue_stale_running_runs(stale_after_seconds=self.stale_running_seconds)
            run = await repo.claim_next_queued_run()
            if run is None:
                return None
            metadata = run.metadata_json if isinstance(run.metadata_json, dict) else {}
            req = ShadowRunRequest(
                ticker=run.ticker,
                trade_date=run.trade_date.isoformat(),
                selected_analysts=list(run.selected_analysts),
                provider=run.provider or os.getenv("TRADINGAGENTS_LLM_PROVIDER", "ollama"),
                deep_model=run.model or os.getenv("TRADINGAGENTS_DEEP_MODEL", "llama3.2:latest"),
                quick_model=run.model or os.getenv("TRADINGAGENTS_QUICK_MODEL", os.getenv("TRADINGAGENTS_DEEP_MODEL", "llama3.2:latest")),
                shadow_run_id=str(run.id),
                target_profile=metadata.get("target_profile") if isinstance(metadata.get("target_profile"), dict) else None,
                checkpoint_enabled=False,
            )
            return QueuedShadowJob(job_id=str(run.id), request=req, metadata={"worker_id": worker_id})

    async def mark_running(self, *, job_id: str, worker_id: str) -> None:
        # claim_next_queued_run already sets RUNNING; keep method for protocol completeness.
        return None

    async def mark_succeeded(self, *, job_id: str, result: ShadowRunResult) -> bool:
        run_id = UUID(job_id)
        factory = create_session_factory(self.db_url)
        async with factory() as session:
            repo = ShadowRunRepository(session)
            current = await repo.get_run_by_id(run_id)
            if current is not None and current.status == ShadowRunStatus.SUCCEEDED:
                return False
            artifacts = [
                ArtifactCreate(
                    artifact_type=item.get("kind", "unknown"),
                    path=item.get("uri", ""),
                    metadata_json={
                        "sha256": item.get("sha256"),
                        "bytes": item.get("bytes"),
                        "content_type": item.get("content_type"),
                    },
                )
                for item in result.artifacts
            ]
            await repo.mark_run_succeeded_atomic(
                run_id=run_id,
                final_rating=result.decision,
                decision_markdown=result.final_trade_decision,
                state_log_dir=result.state_log_dir,
                memory_log_path=result.memory_log_path,
                provider_metadata={
                    "provider": result.provider,
                    "deep_model": result.deep_model,
                    "quick_model": result.quick_model,
                    "quality": result.quality,
                    "telemetry": result.telemetry,
                },
                artifacts=artifacts,
            )
            run = await repo.get_run_by_id(run_id)
            output = await repo.get_output_by_run_id(run_id)
            if run is not None and output is not None:
                quality = output.provider_metadata.get("quality") if isinstance(output.provider_metadata, dict) else {}
                precedent_text = build_precedent_query_text(run=run, output=output, quality=quality if isinstance(quality, dict) else {})
                await repo.upsert_precedent_embedding(
                    run_id=run.id,
                    ticker=run.ticker,
                    trade_date=run.trade_date,
                    content_text=precedent_text,
                    metadata_json={
                        "provider": result.provider,
                        "deep_model": result.deep_model,
                        "quick_model": result.quick_model,
                        "quality_status": (result.quality or {}).get("status"),
                        "final_rating": result.decision,
                        "selected_analysts": list(run.selected_analysts or []),
                    },
                )
                precedent_matches = await repo.search_precedents_for_run(run_id=run.id, limit=3)
                precedent_summary = {
                    "precedent_count": len(precedent_matches),
                    "precedents": [
                        {
                            "run_id": str(match.run_id),
                            "ticker": match.ticker,
                            "trade_date": match.trade_date.isoformat(),
                            "similarity": match.similarity,
                            "content_hash": match.content_hash,
                            "embedding_model": match.embedding_model,
                            "metadata_json": match.metadata_json,
                        }
                        for match in precedent_matches
                    ],
                }
                provider_metadata = dict(output.provider_metadata or {})
                provider_metadata["precedent_summary"] = precedent_summary
                await repo.upsert_output_summary(
                    run_id=run.id,
                    final_rating=output.final_rating,
                    decision_markdown=output.decision_markdown,
                    state_log_dir=output.state_log_dir,
                    memory_log_path=output.memory_log_path,
                    provider_metadata=provider_metadata,
                )
            existing_evaluations = await repo.list_evaluation_runs(shadow_run_id=run_id, limit=1, offset=0)
            if not existing_evaluations:
                run = await repo.get_run_by_id(run_id)
                output = await repo.get_output_by_run_id(run_id)
                stored_artifacts = await repo.get_artifacts_by_run_id(run_id)
                if run is not None and output is not None:
                    rubric = await repo.ensure_evaluation_rubric(
                        name=DEFAULT_RUBRIC_NAME,
                        version=DEFAULT_RUBRIC_VERSION,
                        scope_type="shadow_run",
                        status="active",
                        description="TradingAgents shadow-run evidence, verification, scoring, and judgement rubric.",
                        definition_json=DEFAULT_RUBRIC_DEFINITION,
                    )
                    evaluation_input = build_shadow_run_evaluation_input(
                        run=run,
                        output=output,
                        artifacts=stored_artifacts,
                    )
                    computation = compute_shadow_run_evaluation(
                        evaluation_input=evaluation_input,
                        evaluator_type="system",
                        evaluator_model=None,
                    )
                    await repo.create_completed_evaluation_run(
                        rubric_id=rubric.id,
                        target_type="shadow_run",
                        target_id=run.id,
                        shadow_run_id=run.id,
                        evaluator_type="system",
                        evaluator_model=None,
                        input_json=computation.input_json,
                        result_json=computation.result_json,
                        scores=computation.scores,
                        annotation=computation.annotation,
                        trace_id=None,
                    )
            return True

    async def mark_failed(self, *, job_id: str, error_message: str) -> None:
        run_id = UUID(job_id)
        factory = create_session_factory(self.db_url)
        async with factory() as session:
            repo = ShadowRunRepository(session)
            await repo.set_run_status(run_id=run_id, new_status=ShadowRunStatus.FAILED, error_message=error_message)


@dataclass(frozen=True)
class _DbEventSink(JobEventSink):
    db_url: str | None = None

    async def emit(self, *, job_id: str, event_type: str, payload: dict | None = None) -> None:
        if job_id == "*":
            return
        factory = create_session_factory(self.db_url)
        async with factory() as session:
            repo = ShadowRunRepository(session)
            await repo.append_event(run_id=UUID(job_id), event_type=event_type, payload=payload)


def main() -> None:
    worker_id = os.getenv("WORKER_ID", socket.gethostname())
    db_url = os.getenv("DATABASE_URL")
    repository = _DbJobRepository(
        db_url=db_url,
        stale_running_seconds=int(os.getenv("WORKER_STALE_RUNNING_SECONDS", "1800")),
    )
    event_sink = _DbEventSink(db_url=db_url)
    asyncio.run(
        run_worker_loop(
            repository=repository,
            event_sink=event_sink,
            worker_id=worker_id,
            poll_interval_seconds=float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "1.0")),
        )
    )
