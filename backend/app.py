from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.api.v1 import api_router
from backend.core.config import get_settings
from backend.core.db import Base, SessionLocal, engine
from backend.core.logging import configure_logging
from backend.services.auth import seed_admin
from backend.services.events import event_bus

configure_logging()
settings = get_settings()

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_admin(db, settings.default_admin_email, settings.default_admin_password, settings.default_admin_name)
    finally:
        db.close()


@app.websocket("/ws/v1/analysis/{analysis_id}")
async def analysis_ws(websocket: WebSocket, analysis_id: str):
    await websocket.accept()
    try:
        async for event in event_bus.subscribe(analysis_id):
            await websocket.send_json(event)
            if event.get("type") in {"analysis_completed", "analysis_failed"}:
                break
    except WebSocketDisconnect:
        return
