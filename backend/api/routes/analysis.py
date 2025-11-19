from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, Any

from ..models.schemas import AnalysisRequest, AnalysisStatus, AnalysisResults
from ..services.analysis_service import AnalysisService
from ..websocket.stream_handler import StreamHandler

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# Initialize services (these would be injected via dependency injection in production)
analysis_service = AnalysisService()
stream_handler = StreamHandler(analysis_service)


@router.post("/start", response_model=Dict[str, str])
async def start_analysis(request: AnalysisRequest):
    """Start a new analysis and return analysis_id."""
    # Start analysis first to get the ID
    analysis_id = analysis_service.start_analysis(request, None)
    
    # Create and store update callback that sends to WebSocket
    async def send_update(update):
        await stream_handler.send_update(analysis_id, update)
    
    # Store callback in the analysis data
    if analysis_id in analysis_service.active_analyses:
        analysis_service.active_analyses[analysis_id]["update_callback"] = send_update
    
    return {"analysis_id": analysis_id}


@router.get("/{analysis_id}/status", response_model=AnalysisStatus)
async def get_analysis_status(analysis_id: str):
    """Get the status of an analysis."""
    status = analysis_service.get_analysis_status(analysis_id)
    if not status:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return status


@router.get("/{analysis_id}/results", response_model=Dict[str, Any])
async def get_analysis_results(analysis_id: str):
    """Get the results of a completed analysis."""
    results = analysis_service.get_analysis_results(analysis_id)
    if not results:
        raise HTTPException(
            status_code=404,
            detail="Analysis not found or not completed"
        )
    return results


@router.websocket("/{analysis_id}/stream")
async def stream_analysis_updates(websocket: WebSocket, analysis_id: str):
    """WebSocket endpoint for streaming analysis updates."""
    await stream_handler.handle_stream(websocket, analysis_id)

