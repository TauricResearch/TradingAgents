import json
import pathlib
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from api.models.run import RunConfig, RunResult, RunSummary
from api.services.run_service import RunService
from api.store.runs_store import RunsStore

try:
    from tradingagents.default_config import DEFAULT_CONFIG
except ImportError:
    DEFAULT_CONFIG = {"results_dir": "./results"}

router = APIRouter()
_db_path = pathlib.Path(DEFAULT_CONFIG["results_dir"]) / "runs.sqlite"
_store = RunsStore(_db_path)
_service = RunService(_store)


@router.post("", response_model=RunSummary)
def create_run(config: RunConfig):
    run = _store.create(config)
    return run


@router.get("", response_model=list[RunSummary])
def list_runs():
    return _store.list_all()


@router.get("/{run_id}", response_model=RunResult)
def get_run(run_id: str):
    run = _store.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/stream")
def stream_run(run_id: str):
    run = _store.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    def event_generator():
        for event in _service.stream_events(run_id):
            data = json.dumps(event["data"])
            yield f"event: {event['event']}\ndata: {data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
