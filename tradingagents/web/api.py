"""FastAPI boundary for the localhost-only TradingAgents workbench."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from tradingagents.dataflows.symbol_utils import normalize_symbol
from tradingagents.dataflows.ticker_utils import normalize_ticker_symbol
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.execution.models import ANALYST_WIRE_KEYS, AnalysisRequest
from tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS

from .broker import EventBroker, Keepalive, SubscriptionClosed
from .manager import (
    ActiveRunConflict,
    ResumeRunConflict,
    RunNotActive,
    RunNotResumable,
    RunNotRetryable,
    SingleRunManager,
)
from .schemas import RESEARCH_DEPTHS, SUPPORTED_OUTPUT_LANGUAGES, RunCreateRequest
from .store import (
    InvalidStorePath,
    RunNotFound,
    RunStore,
    RunStoreCorruption,
)


TERMINAL_STREAM_EVENTS = frozenset(
    {"run.completed", "run.failed", "run.cancelled", "run.interrupted"}
)
TERMINAL_STREAM_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "interrupted"}
)
DATA_CREDENTIAL_ENV = {
    "alpha_vantage": ("ALPHA_VANTAGE_API_KEY",),
    "fred": ("FRED_API_KEY",),
    "tavily": ("TAVILY_API_KEY",),
    "tushare": ("TUSHARE_TOKEN", "TUSHARE_API_KEY"),
}
AZURE_REQUIRED_ENV = ("AZURE_OPENAI_ENDPOINT", "OPENAI_API_VERSION")
SAFE_RESUME_MISMATCH_FIELDS = frozenset(
    {
        "abandoned_task_is_durable",
        "abandoned_task_missing",
        "abandoned_tool_already_committed",
        "analysis_date",
        "asset_type",
        "checkpoint_enabled",
        "checkpoint_event_content_mismatch",
        "checkpoint_event_frontier_mismatch",
        "checkpoint_event_frontier_too_far_behind",
        "checkpoint_event_shape",
        "checkpoint_frontier_drift",
        "checkpoint_missing",
        "checkpoint_not_committed",
        "checkpoint_shape",
        "commit_event_without_durable_task",
        "commit_map_shape",
        "commit_task_id_mismatch",
        "commit_token_changed",
        "commit_token_removed",
        "commit_token_schema",
        "commit_token_shape",
        "deep_think_llm",
        "duplicate_checkpoint_event",
        "duplicate_pending_commit",
        "duplicate_task_candidate",
        "duplicate_task_started",
        "durable_task_without_commit_event",
        "effective_config",
        "event_frontier_drift",
        "event_schema_version",
        "fingerprint_integrity",
        "fingerprint_missing",
        "fingerprint_version",
        "initial_context_hash",
        "llm_provider",
        "max_debate_rounds",
        "max_risk_discuss_rounds",
        "missing_task_candidate",
        "observation_frontier",
        "observation_schema",
        "output_language",
        "pending_business_write_without_commit",
        "pending_commit_shape",
        "pending_commit_task_id_mismatch",
        "pending_task_already_committed",
        "pending_write_shape",
        "quick_think_llm",
        "request",
        "resume_eligibility",
        "role_tool_route_mismatch",
        "runtime_environment",
        "runtime_semantics_hash",
        "selected_analysts",
        "task_abandoned_conflict",
        "task_abandoned_shape",
        "task_candidate_artifact",
        "task_candidate_content",
        "task_candidate_token_mismatch",
        "task_committed_twice",
        "task_started_candidate_mismatch",
        "task_started_shape",
        "ticker",
        "tokenless_application_channel_update",
        "tokenless_business_state_change",
        "tokenless_pending_business_write",
        "tool_role_route_mismatch",
        "unproven_initial_tokenless_checkpoint",
    }
)
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors "
        "'none'; form-action 'self'; script-src 'self'; style-src 'self' "
        "'unsafe-inline'; img-src 'self' data:; connect-src 'self'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


class ApiBoundaryError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        fields: tuple[str, ...] = (),
        active_run_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.public_message = message
        self.fields = fields
        self.active_run_id = active_run_id
        super().__init__(message)


def create_app(
    *,
    store: RunStore | None = None,
    broker: EventBroker | None = None,
    manager: SingleRunManager | None = None,
    static_dir: str | Path | None = None,
    environment: Mapping[str, str] | None = None,
    checkpoint_available: bool = True,
    recover_startup: bool = True,
) -> FastAPI:
    """Compose the HTTP layer without importing it from legacy CLI paths."""
    selected_store = store or RunStore()
    selected_broker = broker or EventBroker(selected_store)
    selected_manager = manager or SingleRunManager(selected_store, selected_broker)
    selected_environment = os.environ if environment is None else environment
    assets_root = Path(static_dir or Path(__file__).with_name("static")).resolve()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if recover_startup:
            recover = getattr(selected_manager, "recover_startup", None)
            if callable(recover):
                application.state.recovered_runs = recover()
        yield

    app = FastAPI(
        title="TradingAgents Local Workbench",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.store = selected_store
    app.state.broker = selected_broker
    app.state.manager = selected_manager
    app.state.environment = selected_environment
    app.state.checkpoint_available = checkpoint_available
    app.state.static_dir = assets_root

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response

    @app.exception_handler(ApiBoundaryError)
    async def handle_boundary_error(_request: Request, exc: ApiBoundaryError):
        return _error_response(
            exc.status_code,
            exc.code,
            exc.public_message,
            fields=exc.fields,
            active_run_id=exc.active_run_id,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        _request: Request,
        exc: RequestValidationError,
    ):
        fields = tuple(
            dict.fromkeys(
                ".".join(str(part) for part in error.get("loc", ()) if part != "body")
                or "request"
                for error in exc.errors()
            )
        )
        return _error_response(
            422,
            "validation_error",
            "The request contains invalid fields.",
            fields=fields,
        )

    @app.exception_handler(RunNotFound)
    @app.exception_handler(InvalidStorePath)
    async def handle_missing_run(_request: Request, _exc: Exception):
        return _error_response(404, "not_found", "The requested run or artifact was not found.")

    @app.exception_handler(RunStoreCorruption)
    async def handle_store_corruption(_request: Request, _exc: RunStoreCorruption):
        return _error_response(
            500,
            "history_corrupted",
            "Stored run history failed an integrity check.",
        )

    @app.exception_handler(ActiveRunConflict)
    async def handle_active_conflict(_request: Request, exc: ActiveRunConflict):
        return _error_response(
            409,
            "active_run_conflict",
            "Another analysis is already active.",
            active_run_id=exc.active_run_id,
        )

    @app.exception_handler(RunNotActive)
    async def handle_not_active(_request: Request, _exc: RunNotActive):
        return _error_response(409, "run_not_active", "The run is not active.")

    @app.exception_handler(RunNotRetryable)
    async def handle_not_retryable(_request: Request, _exc: RunNotRetryable):
        return _error_response(409, "run_not_retryable", "The run cannot be retried.")

    @app.exception_handler(RunNotResumable)
    async def handle_not_resumable(_request: Request, _exc: RunNotResumable):
        return _error_response(409, "run_not_resumable", "The run cannot be resumed.")

    @app.exception_handler(ResumeRunConflict)
    async def handle_resume_conflict(_request: Request, exc: ResumeRunConflict):
        return _error_response(
            409,
            "resume_conflict",
            "The stored run is incompatible with the current runtime.",
            fields=_safe_mismatch_fields(exc.fields),
        )

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        return _configuration_payload(
            selected_environment,
            checkpoint_available=checkpoint_available,
        )

    @app.get("/api/runs")
    def list_runs() -> list[dict[str, Any]]:
        return [asdict(summary) for summary in selected_store.list_runs()]

    @app.post("/api/runs", status_code=201)
    def create_run(body: RunCreateRequest) -> dict[str, Any]:
        request_model, configured_keys = _analysis_request(
            body,
            selected_environment,
            checkpoint_available=checkpoint_available,
        )
        return selected_manager.start(
            request_model,
            configured_keys=configured_keys,
        ).as_dict()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        return selected_store.read_snapshot(run_id).as_dict()

    @app.post("/api/runs/{run_id}/cancel", status_code=202)
    def cancel_run(run_id: str) -> dict[str, Any]:
        return selected_manager.cancel(run_id).as_dict()

    @app.post("/api/runs/{run_id}/retry", status_code=201)
    def retry_run(run_id: str) -> dict[str, Any]:
        return selected_manager.retry(run_id).as_dict()

    @app.post("/api/runs/{run_id}/resume", status_code=202)
    def resume_run(run_id: str) -> dict[str, Any]:
        return selected_manager.resume(run_id).as_dict()

    @app.get("/api/runs/{run_id}/artifacts")
    def list_artifacts(run_id: str) -> list[dict[str, Any]]:
        selected_store.read_snapshot(run_id)
        return _artifact_metadata(selected_store, run_id)

    @app.get("/api/runs/{run_id}/artifacts/{artifact_id}")
    def read_artifact(run_id: str, artifact_id: str) -> Response:
        selected_store.read_snapshot(run_id)
        metadata = {
            item["artifact_id"]: item
            for item in _artifact_metadata(selected_store, run_id)
        }
        if artifact_id not in metadata:
            raise RunNotFound(f"artifact {artifact_id}")
        content = selected_store.read_artifact(run_id, artifact_id)
        return Response(
            content=content,
            media_type=str(metadata[artifact_id]["media_type"]),
            headers={"Content-Length": str(len(content))},
        )

    @app.get("/api/runs/{run_id}/events")
    async def stream_events(
        request: Request,
        run_id: str,
        after: int | None = Query(default=None, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        snapshot = selected_store.read_snapshot(run_id)
        cursor = _event_cursor(after, last_event_id)
        subscription = await selected_broker.subscribe(
            run_id,
            after=cursor,
            close_after_replay=snapshot.status in TERMINAL_STREAM_STATUSES,
        )

        async def event_stream():
            try:
                async for item in subscription:
                    if await request.is_disconnected():
                        break
                    if isinstance(item, Keepalive):
                        yield f": {item.comment}\n\n"
                        continue
                    encoded = json.dumps(
                        item.as_dict(),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    yield f"id: {item.sequence}\nevent: {item.type}\ndata: {encoded}\n\n"
                    if item.type in TERMINAL_STREAM_EVENTS:
                        break
            except SubscriptionClosed:
                return
            finally:
                await subscription.close("client_disconnected")

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    if (assets_root / "assets").is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=assets_root / "assets"),
            name="assets",
        )

    @app.get("/{path:path}")
    def spa_fallback(path: str):
        if path == "api" or path.startswith("api/"):
            return _error_response(404, "not_found", "The API route does not exist.")
        index = assets_root / "index.html"
        if index.is_file():
            return FileResponse(index, media_type="text/html")
        return _error_response(
            503,
            "frontend_unavailable",
            "The local frontend assets have not been built yet.",
        )

    return app


def _analysis_request(
    body: RunCreateRequest,
    environment: Mapping[str, str],
    *,
    checkpoint_available: bool,
) -> tuple[AnalysisRequest, dict[str, bool]]:
    provider = body.llm_provider.lower()
    if provider not in PROVIDER_API_KEY_ENV:
        raise ApiBoundaryError(
            422,
            "unsupported_provider",
            "The selected LLM provider is not supported.",
            fields=("llm_provider",),
        )
    _validate_model(provider, body.quick_think_llm, "quick_think_llm", "quick")
    _validate_model(provider, body.deep_think_llm, "deep_think_llm", "deep")

    if not _provider_configured(provider, environment):
        raise ApiBoundaryError(
            422,
            "missing_configuration",
            "The selected LLM provider is not configured on this local server.",
            fields=("llm_provider",),
        )
    if body.checkpoint_enabled and not checkpoint_available:
        raise ApiBoundaryError(
            422,
            "checkpoint_unavailable",
            "Checkpoint resume is unavailable in the current runtime.",
            fields=("checkpoint_enabled",),
        )

    canonical_ticker = normalize_symbol(normalize_ticker_symbol(body.ticker))
    asset_type = _asset_type(canonical_ticker)
    if body.asset_type is not None and body.asset_type != asset_type:
        raise ApiBoundaryError(
            422,
            "asset_type_mismatch",
            "The asset type does not match the normalized ticker.",
            fields=("ticker", "asset_type"),
        )
    if asset_type == "crypto" and "fundamentals" in body.selected_analysts:
        raise ApiBoundaryError(
            422,
            "unsupported_analyst",
            "The fundamentals analyst is unavailable for crypto.",
            fields=("selected_analysts",),
        )

    effective_config = {
        "llm_provider": provider,
        "quick_think_llm": body.quick_think_llm,
        "deep_think_llm": body.deep_think_llm,
        "output_language": body.output_language,
        "checkpoint_enabled": body.checkpoint_enabled,
        "max_debate_rounds": body.research_depth,
        "max_risk_discuss_rounds": body.research_depth,
    }
    configured_keys = _configured_keys(environment)
    return (
        AnalysisRequest(
            ticker=canonical_ticker,
            analysis_date=body.analysis_date,
            asset_type=asset_type,
            selected_analysts=body.selected_analysts,
            max_debate_rounds=body.research_depth,
            max_risk_discuss_rounds=body.research_depth,
            effective_config=effective_config,
        ),
        configured_keys,
    )


def _validate_model(provider: str, model: str, field: str, mode: str) -> None:
    options = MODEL_OPTIONS.get(provider)
    if options is None:
        return
    mode_options = options[mode]
    allowed = {value for _label, value in mode_options if value != "custom"}
    custom_allowed = any(value == "custom" for _label, value in mode_options)
    if model == "custom" or (not custom_allowed and model not in allowed):
        raise ApiBoundaryError(
            422,
            "unsupported_model",
            "The selected model is not available for this provider and mode.",
            fields=(field,),
        )


def _asset_type(ticker: str) -> str:
    crypto_suffixes = ("-USD", "-USDT", "-USDC", "-BTC", "-ETH")
    return "crypto" if ticker.upper().endswith(crypto_suffixes) else "stock"


def _configured_keys(environment: Mapping[str, str]) -> dict[str, bool]:
    configured = {
        provider: _provider_configured(provider, environment)
        for provider in PROVIDER_API_KEY_ENV
    }
    configured.update(
        {
            provider: any(environment.get(env_name) for env_name in env_names)
            for provider, env_names in DATA_CREDENTIAL_ENV.items()
        }
    )
    return configured


def _provider_configured(provider: str, environment: Mapping[str, str]) -> bool:
    env_name = PROVIDER_API_KEY_ENV[provider]
    if env_name is not None and not environment.get(env_name):
        return False
    if provider == "azure" and any(
        not environment.get(required) for required in AZURE_REQUIRED_ENV
    ):
        return False
    return True


def _configuration_payload(
    environment: Mapping[str, str],
    *,
    checkpoint_available: bool,
) -> dict[str, Any]:
    configured = _configured_keys(environment)
    providers = []
    for provider, env_name in PROVIDER_API_KEY_ENV.items():
        modes = MODEL_OPTIONS.get(provider)
        providers.append(
            {
                "id": provider,
                "configured": configured[provider],
                "requires_api_key": env_name is not None,
                "models": {
                    mode: [
                        {"label": label, "id": model_id}
                        for label, model_id in (modes or {}).get(mode, ())
                    ]
                    for mode in ("quick", "deep")
                },
                "custom_model_allowed": modes is None
                or any(
                    model_id == "custom"
                    for options in modes.values()
                    for _label, model_id in options
                ),
            }
        )
    return {
        "providers": providers,
        "configured_keys": configured,
        "analysts": [{"id": analyst} for analyst in ANALYST_WIRE_KEYS],
        "depths": list(RESEARCH_DEPTHS),
        "output_languages": list(SUPPORTED_OUTPUT_LANGUAGES),
        "checkpoint_available": checkpoint_available,
        "defaults": {
            "llm_provider": DEFAULT_CONFIG.get("llm_provider"),
            "quick_think_llm": DEFAULT_CONFIG.get("quick_think_llm"),
            "deep_think_llm": DEFAULT_CONFIG.get("deep_think_llm"),
            "output_language": DEFAULT_CONFIG.get("output_language", "English"),
            "research_depth": DEFAULT_CONFIG.get("max_debate_rounds", 1),
            "checkpoint_enabled": bool(DEFAULT_CONFIG.get("checkpoint_enabled")),
        },
    }


def _artifact_metadata(store: RunStore, run_id: str) -> list[dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for event in store.read_events(run_id):
        if event.type != "artifact.written":
            continue
        payload = event.payload
        artifact_id = payload.get("artifact_id")
        if not isinstance(artifact_id, str):
            continue
        artifacts.setdefault(
            artifact_id,
            {
                "artifact_id": artifact_id,
                "kind": str(payload.get("kind") or "data"),
                "media_type": str(payload.get("media_type") or "application/octet-stream"),
                "content_sha256": str(payload.get("content_sha256") or ""),
                "byte_size": int(payload.get("byte_size") or 0),
                "locator": str(payload.get("locator") or ""),
            },
        )
    return list(artifacts.values())


def _event_cursor(after: int | None, last_event_id: str | None) -> int:
    header_cursor = 0
    if last_event_id is not None:
        try:
            header_cursor = int(last_event_id)
        except ValueError as exc:
            raise ApiBoundaryError(
                400,
                "invalid_event_cursor",
                "Last-Event-ID must be a non-negative integer.",
                fields=("Last-Event-ID",),
            ) from exc
        if header_cursor < 0:
            raise ApiBoundaryError(
                400,
                "invalid_event_cursor",
                "Last-Event-ID must be a non-negative integer.",
                fields=("Last-Event-ID",),
            )
    if after is not None and last_event_id is not None and after != header_cursor:
        raise ApiBoundaryError(
            400,
            "event_cursor_mismatch",
            "The query and Last-Event-ID cursors do not match.",
            fields=("after", "Last-Event-ID"),
        )
    return after if after is not None else header_cursor


def _safe_mismatch_fields(fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(field for field in fields if field in SAFE_RESUME_MISMATCH_FIELDS)
    )


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    fields: tuple[str, ...] = (),
    active_run_id: str | None = None,
) -> JSONResponse:
    detail: dict[str, Any] = {
        "code": code,
        "message": message,
        "fields": list(fields),
    }
    if active_run_id is not None:
        detail["active_run_id"] = active_run_id
    return JSONResponse({"detail": detail}, status_code=status_code)
