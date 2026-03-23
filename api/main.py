from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import runs, settings

app = FastAPI(title="TradingAgents API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs.router, prefix="/runs", tags=["runs"])
app.include_router(settings.router, prefix="/settings", tags=["settings"])
