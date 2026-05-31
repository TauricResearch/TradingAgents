import json
from pathlib import Path
from typing import Any, Iterator

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from tradingagents.default_config import DEFAULT_CONFIG
from web.models import AnalysisRequest, StreamEvent
from web.run_state import run_state
from web.streaming import sse, stream_analysis


STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="TradingAgentsWeb")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _reports_root() -> Path:
    return Path(DEFAULT_CONFIG["results_dir"]).expanduser().resolve()


def _resolve_report_path(report_path: str) -> Path:
    root = _reports_root()
    resolved = (root / report_path).resolve()
    if not resolved.is_file() or not resolved.name.startswith("full_states_log_"):
        raise HTTPException(status_code=404, detail="Report not found")
    if root != resolved and root not in resolved.parents:
        raise HTTPException(status_code=404, detail="Report not found")
    return resolved


def list_saved_reports() -> list[dict[str, Any]]:
    root = _reports_root()
    if not root.exists():
        return []

    reports = []
    for path in root.glob("*/TradingAgentsStrategy_logs/full_states_log_*.json"):
        relative_path = path.relative_to(root).as_posix()
        ticker = path.parents[1].name
        date = path.stem.removeprefix("full_states_log_")
        reports.append(
            {
                "path": relative_path,
                "ticker": ticker,
                "analysis_date": date,
                "modified": path.stat().st_mtime_ns,
            }
        )

    return sorted(reports, key=lambda report: report["modified"], reverse=True)


def clear_all_checkpoints(data_cache_dir: str) -> int:
    from tradingagents.graph.checkpointer import clear_all_checkpoints as clear

    return clear(data_cache_dir)


@app.get("/")
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return PlainTextResponse("TradingAgentsWeb")


@app.post("/api/checkpoints/clear")
def clear_checkpoints():
    cleared = clear_all_checkpoints(DEFAULT_CONFIG["data_cache_dir"])
    return {"cleared": cleared}


@app.get("/api/reports")
def saved_reports():
    return {"reports": list_saved_reports()}


@app.get("/api/reports/load")
def load_saved_report(path: str):
    report_path = _resolve_report_path(path)
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Saved report JSON is invalid") from exc


@app.post("/api/analyze")
def analyze(request: AnalysisRequest):
    try:
        run_id = run_state.start()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    def events() -> Iterator[str]:
        try:
            yield from stream_analysis(request, run_id)
        except Exception as exc:
            yield sse(
                StreamEvent(
                    type="run_failed",
                    payload={"run_id": run_id, "error": str(exc)},
                )
            )
        finally:
            run_state.finish(run_id)

    return StreamingResponse(events(), media_type="text/event-stream")


def main() -> None:
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=False)
