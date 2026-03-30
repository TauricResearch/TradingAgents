from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import logging
import time
from agent_os.backend.store import runs

logger = logging.getLogger("agent_os.websocket")

router = APIRouter(prefix="/ws", tags=["websocket"])

# Polling interval when streaming cached events from a background-task-driven run
_EVENT_POLL_INTERVAL_SECONDS = 0.05

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
    run_type = run_info.get("type", "unknown")

    # Lazy-load events from disk when not in memory.
    # Covers hydrated completed/failed runs and orphaned historical runs that
    # were persisted as "running" before the server stopped.
    if not run_info.get("events"):
        try:
            from tradingagents.portfolio.store_factory import create_report_store
            store = create_report_store(run_id=run_id)
            date = (run_info.get("params") or {}).get("date", "")
            if date:
                disk_events = store.load_run_events(date)
                if disk_events:
                    run_info["events"] = disk_events
                    logger.info("Lazy-loaded %d events from disk run=%s", len(disk_events), run_id)
                if run_info.get("hydrated_from_disk") and run_info.get("status") == "running":
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
            msg = (
                f"Run {run_id} is in unexpected status '{status}'. "
                "Execution must be driven by the backend trigger path."
            )
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
    except asyncio.CancelledError:
        logger.info("WebSocket streaming cancelled run=%s", run_id)
    except Exception as e:
        logger.exception("Error during streaming run=%s", run_id)
        try:
            await websocket.send_json({"type": "system", "message": f"Error: {str(e)}"})
            await websocket.close()
        except Exception:
            pass  # client already gone
