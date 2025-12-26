"""Main FastAPI application."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from spektiv.api.config import settings
from spektiv.api.database import init_db, close_db
from spektiv.api.routes import auth_router, strategies_router
from spektiv.api.middleware import add_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup: Initialize database
    await init_db()
    yield
    # Shutdown: Close database connections
    await close_db()


# Create FastAPI application
app = FastAPI(
    title="TradingAgents API",
    description="FastAPI backend for TradingAgents with JWT authentication",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add error handlers
add_error_handlers(app)

# Register routers
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(strategies_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "message": "TradingAgents API",
        "version": "0.1.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "spektiv.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
