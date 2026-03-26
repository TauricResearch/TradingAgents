from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
import asyncio
import logging
import time
import uuid
from typing import Dict, Any
from agent_os.backend.dependencies import get_current_user
from agent_os.backend.store import runs
from agent_os.backend.services.langgraph_engine import LangGraphEngine
from agent_os.backend.services.mock_engine import MockEngine

logger = logging.getLogger("agent_os.websocket")

router = APIRouter(prefix="/ws", tags=["websocket"])

# Polling interval when streaming cached events from a background-task-driven run
_EVENT_POLL_INTERVAL_SECONDS = 0.05

engine = LangGraphEngine()
_mock_engine = MockEngine()

@router.websocket("/stream/{run_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    run_id: str,
):
    await websocket.accept()
    logger.info("WebSocket connected run=%s", run_id)
    
    if run_id not in runs:
        logger.warning("Run not found run=%s", run_id)
        await websocket.send_json({"type": "system", "message": f"Error: Run {run_id} not found."})
        await websocket.close()
        return

    run_info = runs[run_id]
    run_type = run_info["type"]
    params = run_info.get("params", {})

    # Lazy-load events from disk when not in memory.
    # Covers three cases: hydrated completed/failed runs (events=[]), and orphaned "running"
    # runs where the server restarted mid-run. New genuine runs return [] from disk (safe no-op).
    if not run_info.get("events"):
        try:
            from tradingagents.portfolio.store_factory import create_report_store
            flow_id = run_info.get("flow_id") or run_info.get("short_rid") or run_id[:8]
            store = create_report_store(flow_id=flow_id)
            date = (run_info.get("params") or {}).get("date", "")
            if date:
                disk_events = store.load_run_events(date)
                if disk_events:
                    run_info["events"] = disk_events
                    logger.info("Lazy-loaded %d events from disk run=%s", len(disk_events), run_id)
                    # If still marked "running" but disk has events, the producer is gone
                    # (server restarted mid-run) — mark failed so the replay loop terminates
                    # and the UI shows the partial output with an error indicator.
                    if run_info.get("status") == "running":
                        run_info["status"] = "failed"
                        run_info["error"] = "Run did not complete (server restarted)"
        except Exception:
            logger.warning("Failed to lazy-load events for run=%s", run_id)

    try:
        status = run_info.get("status", "queued")

        if status in ("running", "completed", "failed"):
            # Background task is already executing (or finished) — stream its cached events
            # then wait for completion if still running.
            logger.info(
                "WebSocket streaming from cache run=%s status=%s", run_id, status
            )
            sent = 0
            while True:
                cached = run_info.get("events") or []
                while sent < len(cached):
                    payload = cached[sent]
                    if "timestamp" not in payload:
                        payload["timestamp"] = time.strftime("%H:%M:%S")
                    await websocket.send_json(payload)
                    sent += 1
                current_status = run_info.get("status")
                if current_status in ("completed", "failed"):
                    break
                # Yield to the event loop so the background task can produce more events
                await asyncio.sleep(_EVENT_POLL_INTERVAL_SECONDS)

            if run_info.get("status") == "failed":
                await websocket.send_json(
                    {"type": "system", "message": f"Error: Run failed: {run_info.get('error', 'unknown error')}"}
                )
        else:
            # status == "queued" — WebSocket is the executor (background task didn't start yet)
            stream_gen = None
            if run_type == "mock":
                stream_gen = _mock_engine.run_mock(run_id, params)
            elif run_type == "scan":
                stream_gen = engine.run_scan(run_id, params)
            elif run_type == "pipeline":
                stream_gen = engine.run_pipeline(run_id, params)
            elif run_type == "portfolio":
                stream_gen = engine.run_portfolio(run_id, params)
            elif run_type == "auto":
                stream_gen = engine.run_auto(run_id, params)

            if stream_gen:
                run_info["status"] = "running"
                run_info.setdefault("events", [])
                try:
                    async for payload in stream_gen:
                        run_info["events"].append(payload)
                        if "timestamp" not in payload:
                            payload["timestamp"] = time.strftime("%H:%M:%S")
                        await websocket.send_json(payload)
                        logger.debug(
                            "Sent event type=%s node=%s run=%s",
                            payload.get("type"),
                            payload.get("node_id"),
                            run_id,
                        )
                    run_info["status"] = "completed"
                except Exception as exc:
                    run_info["status"] = "failed"
                    run_info["error"] = str(exc)
                    raise
            else:
                msg = f"Run type '{run_type}' streaming not yet implemented."
                logger.warning(msg)
                run_info["status"] = "failed"
                run_info["error"] = msg
                await websocket.send_json({"type": "system", "message": f"Error: {msg}"})

        if run_info.get("status") == "completed":
            await websocket.send_json({"type": "system", "message": "Run completed."})
            logger.info("Run completed run=%s type=%s", run_id, run_type)
        else:
            logger.info("Run ended with status=%s run=%s type=%s", run_info.get("status"), run_id, run_type)
        
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected run=%s", run_id)
    except Exception as e:
        logger.exception("Error during streaming run=%s", run_id)
        try:
            await websocket.send_json({"type": "system", "message": f"Error: {str(e)}"})
            await websocket.close()
        except Exception:
            pass  # client already gone
