from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
import asyncio
import logging
import time
import uuid
from typing import Dict, Any
from agent_os.backend.dependencies import get_current_user
from agent_os.backend.store import runs
from agent_os.backend.services.langgraph_engine import LangGraphEngine

logger = logging.getLogger("agent_os.websocket")

router = APIRouter(prefix="/ws", tags=["websocket"])

engine = LangGraphEngine()

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

    try:
        stream_gen = None
        if run_type == "scan":
            stream_gen = engine.run_scan(run_id, params)
        elif run_type == "pipeline":
            stream_gen = engine.run_pipeline(run_id, params)
        elif run_type == "portfolio":
            stream_gen = engine.run_portfolio(run_id, params)
        elif run_type == "auto":
            stream_gen = engine.run_auto(run_id, params)
        
        if stream_gen:
            async for payload in stream_gen:
                # Add timestamp if not present
                if "timestamp" not in payload:
                    payload["timestamp"] = time.strftime("%H:%M:%S")
                await websocket.send_json(payload)
                logger.debug(
                    "Sent event type=%s node=%s run=%s",
                    payload.get("type"),
                    payload.get("node_id"),
                    run_id,
                )
        else:
            msg = f"Run type '{run_type}' streaming not yet implemented."
            logger.warning(msg)
            await websocket.send_json({"type": "system", "message": f"Error: {msg}"})
            
        await websocket.send_json({"type": "system", "message": "Run completed."})
        logger.info("Run completed run=%s type=%s", run_id, run_type)
        
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected run=%s", run_id)
    except Exception as e:
        logger.exception("Error during streaming run=%s", run_id)
        try:
            await websocket.send_json({"type": "system", "message": f"Error: {str(e)}"})
            await websocket.close()
        except Exception:
            pass  # client already gone
