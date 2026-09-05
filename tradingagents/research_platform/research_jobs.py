"""Controlled local background jobs for the personal research workflow."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .agent_contracts import TradeDirection, TradeHorizon, TradeSignal
from .artifact_store import JsonArtifactStore
from .data_contracts import DataProvider
from .multi_agent_research import MultiAgentResearchProvider
from .narrative_provider import (
    NarrativeMode,
    OpenAIResearchNarrativeProvider,
    ResearchNarrativeProvider,
)
from .research_workflow import ResearchWorkflowConfig, run_ticker_research
from .risk_contracts import RiskPolicy
from .run_archive import JsonResearchRunArchive
from .tushare_provider import TushareProProvider, supports_tushare_symbol
from .yfinance_provider import YFinanceProvider


class ResearchDataProvider(str, Enum):
    """Supported vendor adapters for a local research job."""

    AUTO = "auto"
    TUSHARE = "tushare"
    YFINANCE = "yfinance"


class ResearchJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ManualSignalRequest(BaseModel):
    """Explicit human decision to validate through risk and backtest layers."""

    model_config = ConfigDict(frozen=True)

    direction: TradeDirection
    horizon: TradeHorizon = TradeHorizon.MEDIUM
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    proposed_position_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=2_000)
    expected_return_pct: float | None = None
    stop_loss_pct: float | None = Field(default=None, ge=0.0, le=1.0)


class ResearchJobRequest(BaseModel):
    """Bounded input accepted by the local cockpit research launcher."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    as_of_date: date = Field(default_factory=date.today)
    lookback_days: int = Field(default=90, ge=1, le=3650)
    currency: str | None = None
    manual_signal: ManualSignalRequest | None = None
    narrative_mode: NarrativeMode = NarrativeMode.DETERMINISTIC
    data_provider: ResearchDataProvider = ResearchDataProvider.AUTO

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")
        return normalized


class ResearchJob(BaseModel):
    """Status record for one local research execution."""

    model_config = ConfigDict(frozen=True)

    job_id: str = Field(min_length=1)
    request: ResearchJobRequest
    status: ResearchJobStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    report_path: Path | None = None
    run_id: str | None = None
    error: str | None = None
    phase: str = "queued"


def resolve_data_provider(request: ResearchJobRequest) -> ResearchDataProvider:
    """Resolve the requested vendor without constructing a provider or reading credentials."""

    if request.data_provider != ResearchDataProvider.AUTO:
        return request.data_provider
    return (
        ResearchDataProvider.TUSHARE
        if supports_tushare_symbol(request.symbol)
        else ResearchDataProvider.YFINANCE
    )


ProviderFactory = Callable[[ResearchJobRequest], DataProvider]
NarrativeProviderFactory = Callable[[ResearchJobRequest], ResearchNarrativeProvider]


class LocalResearchJobRunner:
    """Single-worker runner for a local research directory.

    The runner deliberately executes one task at a time. This avoids duplicate
    yfinance requests and keeps cache/report writes predictable for a single
    personal workstation. Completed research is persisted by the workflow;
    the in-memory job list is only a live status surface for the cockpit.
    """

    def __init__(
        self,
        data_dir: str | Path,
        *,
        provider_factory: ProviderFactory | None = None,
        narrative_provider_factory: NarrativeProviderFactory | None = None,
    ):
        self.data_dir = Path(data_dir)
        self.provider_factory = provider_factory or self._default_provider_factory
        self.narrative_provider_factory = (
            narrative_provider_factory or self._default_narrative_provider_factory
        )
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research-job")
        self._jobs: dict[str, ResearchJob] = {}
        self._futures: dict[str, Future[None]] = {}
        self._lock = Lock()

    def submit(self, request: ResearchJobRequest) -> ResearchJob:
        """Queue one bounded local research run."""

        now = _utc_now()
        job = ResearchJob(
            job_id=uuid4().hex,
            request=request,
            status=ResearchJobStatus.QUEUED,
            created_at=now,
        )
        with self._lock:
            self._jobs[job.job_id] = job
            self._futures[job.job_id] = self._executor.submit(self._execute, job.job_id)
        return job

    def get(self, job_id: str) -> ResearchJob | None:
        """Return a job status record when it belongs to this server process."""

        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[ResearchJob]:
        """List newest jobs first for the local cockpit."""

        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def wait(self, job_id: str, timeout: float | None = None) -> ResearchJob:
        """Wait for a job in tests or local scripts, then return its final state."""

        with self._lock:
            future = self._futures.get(job_id)
        if future is None:
            raise KeyError(job_id)
        future.result(timeout=timeout)
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def shutdown(self) -> None:
        """Release the worker used by this local server."""

        self._executor.shutdown(wait=False, cancel_futures=False)

    def _execute(self, job_id: str) -> None:
        self._update(
            job_id,
            status=ResearchJobStatus.RUNNING,
            started_at=_utc_now(),
            phase="collecting_normalized_evidence",
        )
        job = self.get(job_id)
        if job is None:
            return
        try:
            provider = self.provider_factory(job.request)
            narrative_provider = None
            if job.request.narrative_mode in {
                NarrativeMode.OPENAI_NARRATIVE,
                NarrativeMode.MULTI_AGENT_RESEARCH,
            }:
                self._update(job_id, phase="configuring_llm_research")
                narrative_provider = self.narrative_provider_factory(job.request)
                progress_setter = getattr(narrative_provider, "set_progress_callback", None)
                if callable(progress_setter):
                    progress_setter(lambda phase: self._update(job_id, phase=phase))
            self._update(job_id, phase="running_research_workflow")
            signal = _build_manual_signal(job.request)
            result = run_ticker_research(
                config=ResearchWorkflowConfig(
                    symbol=job.request.symbol,
                    as_of_date=job.request.as_of_date,
                    lookback_days=job.request.lookback_days,
                    currency=job.request.currency,
                    narrative_mode=job.request.narrative_mode.value,
                ),
                provider=provider,
                store=JsonArtifactStore(self.data_dir),
                archive=JsonResearchRunArchive(self.data_dir),
                signal=signal,
                risk_policy=RiskPolicy(),
                output_dir=self.data_dir / "reports",
                narrative_provider=narrative_provider,
            )
        except Exception as error:  # Provider errors become visible job state, not server crashes.
            self._update(
                job_id,
                status=ResearchJobStatus.FAILED,
                completed_at=_utc_now(),
                error=str(error) or error.__class__.__name__,
                phase="failed",
            )
            return

        self._update(
            job_id,
            status=ResearchJobStatus.SUCCEEDED,
            completed_at=_utc_now(),
            report_path=result.report_path,
            run_id=result.archived_run.run_id if result.archived_run is not None else None,
            phase="completed",
        )

    def _update(self, job_id: str, **updates: object) -> None:
        with self._lock:
            current = self._jobs.get(job_id)
            if current is not None:
                self._jobs[job_id] = current.model_copy(update=updates)

    def _default_provider_factory(self, request: ResearchJobRequest) -> DataProvider:
        provider = resolve_data_provider(request)
        if provider == ResearchDataProvider.TUSHARE:
            return TushareProProvider()
        return YFinanceProvider(cache_dir=self.data_dir / "yfinance")

    def _default_narrative_provider_factory(
        self,
        request: ResearchJobRequest,
    ) -> ResearchNarrativeProvider:
        if request.narrative_mode == NarrativeMode.MULTI_AGENT_RESEARCH:
            return MultiAgentResearchProvider.from_environment()
        return OpenAIResearchNarrativeProvider.from_environment()


def _build_manual_signal(request: ResearchJobRequest) -> TradeSignal | None:
    if request.manual_signal is None:
        return None
    decision = request.manual_signal
    return TradeSignal(
        symbol=request.symbol,
        as_of_date=request.as_of_date,
        direction=decision.direction,
        horizon=decision.horizon,
        confidence=decision.confidence,
        rationale=decision.rationale,
        proposed_position_pct=decision.proposed_position_pct,
        expected_return_pct=decision.expected_return_pct,
        stop_loss_pct=decision.stop_loss_pct,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
