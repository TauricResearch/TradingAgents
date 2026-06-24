import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from api.database import init_db, seed_global_watchlist
from api.scheduler import scheduler
from api.routers import (
    health,
    signals,
    stream,
    watchlist,
    tickers,
    stats,
    analyze,
    admin,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_global_watchlist()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(
    title="Pulse Trading Signals",
    description="AI-powered institutional-grade trading signals microservice.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to Pulse frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in [
    health.router,
    signals.router,
    stream.router,
    watchlist.router,
    tickers.router,
    stats.router,
    analyze.router,
    admin.router,
]:
    app.include_router(router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")
