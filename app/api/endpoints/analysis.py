from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from app.api import deps
from app.core.schemas.analysis import AnalysisSession, AnalysisSessionCreate
from app.domain.models import User as UserModel
from app.core.services.trading_analysis import TradingAnalysisService
from app.core.websocket_manager import WebSocketManager
from sqlmodel import Session
from cli.utils import SHALLOW_AGENT_OPTIONS, DEEP_AGENT_OPTIONS, BASE_URLS

router = APIRouter()
manager = WebSocketManager()

@router.post("/start", response_model=AnalysisSession)
def start_analysis(
    *,
    analysis_in: AnalysisSessionCreate,
    background_tasks: BackgroundTasks,
    service: TradingAnalysisService = Depends(deps.get_analysis_service),
) -> Any:
    """
    Start a new analysis session.
    """
    session = service.create_session(analysis_in=analysis_in)
    background_tasks.add_task(service.run_analysis, session_id=session.id)
    return session

@router.get("/history", response_model=List[AnalysisSession])
def get_analysis_history(
    service: TradingAnalysisService = Depends(deps.get_analysis_service),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Get analysis history for the current user.
    """
    return service.get_user_sessions(skip=skip, limit=limit)

@router.get("/options")
def get_analysis_options():
    """
    Get available options for analysis.
    """
    return {
        'analysts': [
            {'value': 'market', 'label': 'Market Analyst'},
            {'value': 'social', 'label': 'Social Analyst'},
            {'value': 'news', 'label': 'News Analyst'},
            {'value': 'fundamentals', 'label': 'Fundamentals Analyst'},
        ],
        'research_depths': [
            {'value': 1, 'label': 'Shallow'},
            {'value': 3, 'label': 'Medium'},
            {'value': 5, 'label': 'Deep'},
        ],
        'llm_providers': [{'name': p[0], 'url': p[1]} for p in BASE_URLS],
        'shallow_thinkers': SHALLOW_AGENT_OPTIONS,
        'deep_thinkers': DEEP_AGENT_OPTIONS,
    }

@router.get("/{session_id}", response_model=AnalysisSession)
def get_analysis_session(
    session_id: int,
    service: TradingAnalysisService = Depends(deps.get_analysis_service),
) -> Any:
    """
    Get a specific analysis session by ID.
    """
    session = service.get_session(session_id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Analysis session not found")
    return session

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str,
    db: Session = Depends(deps.get_db)
):
    """
    WebSocket endpoint for real-time analysis updates.
    """
    user = deps.get_user_from_token(token=token, db=db)
    if not user or not user.is_active:
        await websocket.close(code=1008)
        return

    await manager.connect(user.id, websocket)
    try:
        while True:
            # Keep the connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user.id, websocket)