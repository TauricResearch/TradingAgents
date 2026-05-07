import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent_os.backend.routes.runs import _ensure_run_events_loaded
from agent_os.backend.store import runs

logger = logging.getLogger("agent_os.websocket")

router = APIRouter(prefix="/ws", tags=["websocket"])

# Polling interval when streaming cached events from a background-task-driven run
_EVENT_POLL_INTERVAL_SECONDS = 0.05
# Send a lightweight keepalive when a run is active but temporarily quiet.
_HEARTBEAT_INTERVAL_SECONDS = 10.0


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
    await _ensure_run_events_loaded(run_id)
    if run_info.get("hydrated_from_disk") and run_info.get("status") == "running":
        run_info["status"] = "failed"
        run_info["error"] = "Run did not complete (server restarted)"

    try:
        status = run_info.get("status", "queued")

        if status in ("running", "completed", "failed", "awaiting_decision"):
            # Background task is already executing (or finished) — stream its cached events
            # then wait for completion if still running.
            logger.info("WebSocket streaming from cache run=%s status=%s", run_id, status)
            sent = 0
            last_send_monotonic = time.monotonic()
            while True:
                cached = run_info.get("events") or []
                while sent < len(cached):
                    payload = cached[sent]
                    if "timestamp" not in payload:
                        payload["timestamp"] = time.strftime("%H:%M:%S")
                    await websocket.send_json(payload)
                    sent += 1
                    last_send_monotonic = time.monotonic()
                current_status = run_info.get("status")
                if current_status in ("completed", "failed", "awaiting_decision"):
                    break
                if time.monotonic() - last_send_monotonic >= _HEARTBEAT_INTERVAL_SECONDS:
                    await websocket.send_json(
                        {
                            "type": "system",
                            "message": "__heartbeat__",
                            "timestamp": time.strftime("%H:%M:%S"),
                        }
                    )
                    last_send_monotonic = time.monotonic()
                # Yield to the event loop so the background task can produce more events
                await asyncio.sleep(_EVENT_POLL_INTERVAL_SECONDS)

            if run_info.get("status") == "failed":
                await websocket.send_json(
                    {
                        "type": "system",
                        "message": f"Error: Run failed: {run_info.get('error', 'unknown error')}",
                    }
                )
            elif run_info.get("status") == "awaiting_decision":
                await websocket.send_json(
                    {
                        "type": "system",
                        "message": "Run paused awaiting Phase 3 decision.",
                        "run_status": "awaiting_decision",
                        "pending_phase3_decision": run_info.get("pending_phase3_decision"),
                    }
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
        elif run_info.get("status") == "awaiting_decision":
            logger.info("Run paused awaiting decision run=%s type=%s", run_id, run_type)
        else:
            logger.info(
                "Run ended with status=%s run=%s type=%s", run_info.get("status"), run_id, run_type
            )

        try:
            await websocket.close()
        except Exception:
            logger.debug("WebSocket already closed run=%s", run_id)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected run=%s", run_id)
    except asyncio.CancelledError:
        logger.info("WebSocket streaming cancelled run=%s", run_id)
    except Exception as e:
        logger.exception("Error during streaming run=%s", run_id)
        try:
            await websocket.send_json({"type": "system", "message": "Internal streaming error"})
            await websocket.close()
        except Exception:
            pass  # client already gone
