"""Local-only FastAPI research workspace."""

from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from tradingagents.dataflows.errors import ProviderRateLimitedError
from tradingagents.dataflows.symbol_utils import normalize_symbol
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.instruments import AssetType, InstrumentNotFoundError, resolve_instrument
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.model_catalog import get_model_options
from tradingagents.persistence import BackupService, Database, Repository
from tradingagents.services.analysis_service import (
    DemoAnalysisService,
    GraphAnalysisService,
    _demo_snapshot,
    has_valid_checkpoint,
)
from tradingagents.services.artifact_service import ArtifactService
from tradingagents.services.conversation_service import (
    ConversationNotFoundError,
    ConversationService,
    DeterministicChatResponder,
    LLMChatResponder,
)
from tradingagents.usage import BudgetExhaustedError, BudgetLimits, BudgetTracker
from tradingagents.usage.budget import summarize_usage

from .jobs import JobBusyError, JobManager, JobResumeError, JobRetryError
from .schemas import (
    AnalysisCreate,
    ConversationMessageCreate,
    ReevaluateCreate,
    ResolveRequest,
    RestoreRequest,
)
from .yahoo_resilience import CachedYahooProvider


def _demo_identity(symbol: str) -> dict[str, str]:
    values = {
        "SPY": {"company_name": "SPDR S&P 500 ETF Trust", "quote_type": "ETF", "exchange": "PCX", "currency": "USD"},
        "VFIAX": {"company_name": "Vanguard 500 Index Admiral", "quote_type": "MUTUALFUND", "exchange": "NAS", "currency": "USD"},
        "AAPL": {"company_name": "Apple Inc.", "quote_type": "EQUITY", "exchange": "NMS", "currency": "USD"},
        "BTC-USD": {"company_name": "Bitcoin USD", "quote_type": "CRYPTOCURRENCY", "exchange": "CCC", "currency": "USD"},
        "EMPTY": {"company_name": "Holdings Coverage Example", "quote_type": "ETF", "exchange": "PCX", "currency": "USD"},
        "FAIL": {"company_name": "Provider Failure Example", "quote_type": "ETF", "exchange": "PCX", "currency": "USD"},
        "RATE": {"company_name": "Rate Limit Recovery Example", "quote_type": "ETF", "exchange": "PCX", "currency": "USD"},
        "SLOW": {"company_name": "Cancellation Example Fund", "quote_type": "ETF", "exchange": "PCX", "currency": "USD"},
    }
    return values.get(symbol.upper(), {})


def _trust_json(value) -> dict[str, Any] | None:
    return asdict(value) if value else None


def _advice_json(value) -> dict[str, Any]:
    result = asdict(value)
    result["trigger_message_ids"] = list(value.trigger_message_ids)
    return result


def _default_database() -> Database:
    path = os.getenv(
        "TRADINGAGENTS_WEB_DB_PATH",
        str(Path.home() / ".tradingagents" / "web" / "tradingagents.db"),
    )
    return Database(path)


def _demo_fresh_data(report: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(report)
    today = date.today().isoformat()
    value["trade_date"] = today
    snapshot = value.get("fund_snapshot") or _demo_snapshot(
        str(value.get("company_of_interest", "SPY")), str(value.get("asset_type", "fund"))
    )
    if snapshot:
        points = snapshot.setdefault("price_series", [])
        latest = float(points[-1]["adjusted_close"]) if points else 100.0
        points.append({"date": today, "adjusted_close": round(latest + 1, 2), "benchmark": latest})
        snapshot["observed_at"] = datetime.now(UTC).isoformat()
        value["fund_snapshot"] = snapshot
    return value


def create_app(
    *,
    demo: bool | None = None,
    manager: JobManager | None = None,
    repository: Repository | None = None,
) -> FastAPI:
    demo = (os.getenv("TRADINGAGENTS_WEB_DEMO") == "1") if demo is None else demo
    if manager is not None:
        repository = manager.repository
    repository = repository or Repository(_default_database())
    artifact_service = ArtifactService(repository)
    limits = BudgetLimits.from_env()
    yahoo = CachedYahooProvider(repository)

    def analysis_preflight(job, request: dict[str, Any]) -> dict[str, Any]:
        if demo:
            if str(request["symbol"]).upper() == "RATE" and job.record.retry_attempt == 0:
                raise ProviderRateLimitedError("yahoo_finance", cache_status="miss")
            identity = _demo_identity(str(request["symbol"]))
            descriptor = resolve_instrument(
                str(request["symbol"]),
                str(request["asset_type"]),
                identity_resolver=_demo_identity,
                price_probe=lambda _symbol: True,
            )
            cache_status = "demo"
        else:
            resolved = yahoo.resolve(
                str(request["symbol"]),
                str(request["asset_type"]),
                str(request["analysis_date"]),
            )
            descriptor, identity, cache_status = (
                resolved.descriptor,
                resolved.identity,
                resolved.cache_status,
            )
        value = dict(request)
        value["symbol"] = descriptor.canonical_symbol
        value["asset_type"] = descriptor.asset_type.value
        value["_instrument_identity"] = identity
        value["_provider_cache_status"] = cache_status
        if not demo and descriptor.asset_type == AssetType.FUND:
            snapshot, snapshot_cache_status = yahoo.fund_snapshot(
                descriptor,
                str(request["analysis_date"]),
                str(request.get("benchmark_symbol") or "SPY"),
            )
            snapshot["analysis_date"] = str(request["analysis_date"])
            snapshot["benchmark_symbol"] = str(request.get("benchmark_symbol") or "SPY")
            value["_fund_snapshot"] = snapshot
            value["_provider_cache_status"] = snapshot_cache_status
        return value

    def live_fresh_data(report: dict[str, Any]) -> dict[str, Any]:
        if report.get("asset_type") != "fund":
            raise RuntimeError("FRESH_DATA_UNAVAILABLE_FOR_ASSET")
        symbol = str(report.get("company_of_interest"))
        today = date.today().isoformat()
        resolved = yahoo.resolve(symbol, "fund", today)
        snapshot, _cache_status = yahoo.fund_snapshot(
            resolved.descriptor,
            today,
            str(report.get("benchmark_symbol") or "SPY"),
        )
        value = deepcopy(report)
        value["trade_date"] = today
        value["fund_snapshot"] = snapshot
        return value

    if manager is None:
        service = DemoAnalysisService() if demo else GraphAnalysisService()
        manager = JobManager(
            service,
            repository=repository,
            completion_handler=artifact_service.persist_analysis,
            checkpoint_validator=(
                None if demo else lambda record: has_valid_checkpoint(record.request)
            ),
            budget_factory=(
                None
                if demo
                else lambda job: BudgetTracker(
                    repository,
                    job_id=job.id,
                    provider=str(job.request["llm_provider"]),
                    limits=limits,
                )
            ),
            preflight=analysis_preflight,
        )
    else:
        if manager.completion_handler is None:
            manager.completion_handler = artifact_service.persist_analysis
        if manager.preflight is None:
            manager.preflight = analysis_preflight

    def responder_factory(request: dict[str, Any]):
        if demo:
            return DeterministicChatResponder()
        return LLMChatResponder(
            provider=str(request.get("llm_provider") or DEFAULT_CONFIG["llm_provider"]),
            model=str(request.get("quick_model") or DEFAULT_CONFIG["quick_think_llm"]),
            base_url=DEFAULT_CONFIG.get("backend_url"),
        )

    conversations = ConversationService(
        repository,
        responder_factory=responder_factory,
        fresh_data_fetcher=_demo_fresh_data if demo else live_fresh_data,
        budget_limits=limits,
    )
    backups = BackupService(repository.database)
    app = FastAPI(title="TradingAgents Research Workspace", version="0.3.0")
    app.state.jobs = manager
    app.state.repository = repository
    app.state.conversations = conversations
    app.state.backups = backups
    app.state.demo = demo
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[os.getenv("TRADINGAGENTS_WEB_ORIGIN", "http://127.0.0.1:5173")],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )

    @app.on_event("shutdown")
    def shutdown() -> None:
        manager.shutdown()

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "demo" if demo else "live"}

    @app.get("/api/config/options")
    def options():
        providers = []
        for provider in ("ciii", "openai", "anthropic", "google", "ollama", "openai_compatible"):
            key_name = get_api_key_env(provider)
            configured = demo or (not key_name or bool(os.getenv(key_name)))
            if not demo and provider in {"ciii", "openai_compatible"}:
                configured = configured and bool(
                    os.getenv("TRADINGAGENTS_CIII_BASE_URL" if provider == "ciii" else "TRADINGAGENTS_LLM_BACKEND_URL")
                )
            providers.append({
                "id": provider,
                "configured": configured,
                "models": {
                    "quick": [value for _, value in get_model_options(provider, "quick")][:12],
                    "deep": [value for _, value in get_model_options(provider, "deep")][:12],
                },
            })
        tracker = BudgetTracker(repository, provider="ciii", limits=limits)
        return {
            "asset_types": ["auto", "stock", "fund", "crypto"],
            "analysts": ["market", "social", "news", "fundamentals"],
            "languages": ["English", "Chinese", "Spanish", "French", "Japanese"],
            "providers": providers,
            "budget": tracker.preflight(),
        }

    @app.post("/api/instruments/resolve")
    def resolve(body: ResolveRequest):
        try:
            if demo:
                descriptor = resolve_instrument(
                    body.symbol,
                    body.asset_type,
                    identity_resolver=_demo_identity,
                    price_probe=lambda _symbol: True,
                )
            else:
                descriptor = yahoo.resolve(body.symbol, body.asset_type, date.today().isoformat()).descriptor
        except InstrumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "INSTRUMENT_NOT_FOUND", "message": str(exc)}) from exc
        except ProviderRateLimitedError as exc:
            raise HTTPException(status_code=429, detail=exc.public_detail()) from exc
        return descriptor.to_dict()

    @app.get("/api/analyses")
    def list_analyses(limit: int = 100):
        return {"items": manager.list(limit=min(max(limit, 1), 500))}

    @app.post("/api/analyses", status_code=202)
    def create_analysis(body: AnalysisCreate):
        request_data = body.model_dump(mode="json")
        # Only normalization is allowed on the request thread. Yahoo probing is
        # worker work so a provider throttle still leaves a durable job record.
        request_data["symbol"] = normalize_symbol(body.symbol)
        if body.research_depth > limits.max_debate_rounds:
            raise HTTPException(status_code=409, detail={"code": "MAX_DEBATE_ROUNDS_EXCEEDED", "message": "Research depth exceeds the configured deterministic budget"})
        try:
            job = manager.create(request_data)
        except JobBusyError as exc:
            raise HTTPException(status_code=409, detail={"code": "JOB_BUSY", "message": str(exc)}) from exc
        return {"job_id": job.id, "status": job.status}

    def require_job(job_id: str):
        job = manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND", "message": "Unknown analysis job"})
        return job

    @app.get("/api/analyses/{job_id}")
    def get_analysis(job_id: str):
        return require_job(job_id).public()

    @app.get("/api/analyses/{job_id}/events")
    def events(job_id: str, request: Request, last_event_id: str | None = Header(default=None)):
        job = require_job(job_id)
        raw = last_event_id or request.query_params.get("last_event_id") or "0"
        try:
            cursor = max(0, int(raw))
        except ValueError:
            cursor = 0
        return StreamingResponse(
            manager.event_stream(job, cursor),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/analyses/{job_id}/cancel")
    def cancel(job_id: str):
        job = require_job(job_id)
        manager.cancel(job)
        return {"job_id": job.id, "status": job.status}

    @app.post("/api/analyses/{job_id}/resume")
    def resume(job_id: str):
        job = require_job(job_id)
        try:
            manager.resume(job)
        except (JobResumeError, JobBusyError) as exc:
            raise HTTPException(status_code=409, detail={"code": "JOB_NOT_RESUMABLE", "message": str(exc)}) from exc
        return {"job_id": job.id, "status": job.status}

    @app.post("/api/analyses/{job_id}/retry", status_code=202)
    def retry(job_id: str):
        job = require_job(job_id)
        try:
            child = manager.retry(job)
        except (JobRetryError, JobBusyError) as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "JOB_NOT_PROVIDER_RATE_LIMITED", "message": str(exc)},
            ) from exc
        return {
            "job_id": child.id,
            "status": child.status,
            "retry_of_job_id": job.id,
        }

    @app.get("/api/analyses/{job_id}/report.md")
    def report(job_id: str):
        job = require_job(job_id)
        if job.status == "provider_rate_limited":
            raise HTTPException(status_code=409, detail=job.error or {
                "code": "PROVIDER_RATE_LIMITED",
                "message": "Yahoo Finance is temporarily rate limited. Try again later.",
            })
        persisted = repository.get_report_for_job(job.id)
        if persisted is None:
            raise HTTPException(status_code=409, detail={"code": "REPORT_NOT_READY", "message": "Report is not ready"})
        title = str(persisted.result.get("company_of_interest", job.request["symbol"]))
        filename = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in title)[:48]
        return PlainTextResponse(
            persisted.markdown,
            headers={"Content-Disposition": f'attachment; filename="{filename}_report.md"'},
        )

    @app.get("/api/analyses/{job_id}/usage")
    def usage(job_id: str):
        require_job(job_id)
        records = repository.list_usage(job_id=job_id)
        return {"summary": summarize_usage(records, limits=limits), "records": [asdict(item) for item in records]}

    @app.get("/api/analyses/{job_id}/trust")
    def trust(job_id: str):
        require_job(job_id)
        value = repository.latest_trust(job_id=job_id)
        if value is None:
            raise HTTPException(status_code=409, detail={"code": "TRUST_NOT_READY", "message": "Trust assessment is not ready"})
        return _trust_json(value)

    @app.get("/api/reports/{report_id}/versions")
    def versions(report_id: str):
        if repository.get_report(report_id) is None:
            raise HTTPException(status_code=404, detail={"code": "REPORT_NOT_FOUND", "message": "Unknown report"})
        return {"items": [_advice_json(item) for item in repository.list_advice(report_id)]}

    @app.post("/api/reports/{report_id}/conversations", status_code=201)
    def create_conversation(report_id: str):
        try:
            value = conversations.create(report_id)
        except ConversationNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "REPORT_NOT_FOUND", "message": "Unknown report"}) from exc
        return asdict(value)

    @app.get("/api/conversations/{conversation_id}")
    def get_conversation(conversation_id: str):
        try:
            conversation, messages = conversations.get(conversation_id)
        except ConversationNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Unknown conversation"}) from exc
        return {**asdict(conversation), "messages": [asdict(item) for item in messages]}

    @app.post("/api/conversations/{conversation_id}/messages", status_code=201)
    def add_message(conversation_id: str, body: ConversationMessageCreate):
        try:
            user, assistant = conversations.ask(
                conversation_id,
                body.content,
                refresh_data=body.refresh_data,
                candidate_adjustment=body.candidate_adjustment,
            )
        except ConversationNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Unknown conversation"}) from exc
        except BudgetExhaustedError as exc:
            raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.reason}) from exc
        except ProviderRateLimitedError as exc:
            raise HTTPException(status_code=429, detail=exc.public_detail()) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail={"code": "FRESH_DATA_UNAVAILABLE", "message": str(exc)}) from exc
        return {"user": asdict(user), "assistant": asdict(assistant)}

    @app.post("/api/conversations/{conversation_id}/re-evaluate", status_code=201)
    def reevaluate(conversation_id: str, body: ReevaluateCreate):
        try:
            advice = conversations.re_evaluate(
                conversation_id, trigger_message_ids=body.trigger_message_ids
            )
        except ConversationNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Unknown conversation"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": str(exc), "message": "Re-evaluation could not be created"}) from exc
        return _advice_json(advice)

    @app.get("/api/admin/backups")
    def list_backups():
        return {"items": [asdict(item) for item in backups.list()]}

    @app.post("/api/admin/backup", status_code=201)
    def create_backup():
        return asdict(backups.create())

    @app.post("/api/admin/restore/preview")
    def restore_preview(body: RestoreRequest):
        return asdict(backups.preview(body.backup_id))

    @app.post("/api/admin/restore/commit")
    def restore_commit(body: RestoreRequest):
        if repository.active_count():
            raise HTTPException(status_code=409, detail={"code": "ACTIVE_JOB", "message": "Cannot restore while an analysis is active"})
        try:
            value = backups.restore(body.backup_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": str(exc), "message": "Backup cannot be restored"}) from exc
        return {**asdict(value), "restored": True}

    dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
