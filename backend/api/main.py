from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import sys
from pathlib import Path

# Add parent directory to path to import tradingagents
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from .routes import analysis_router, history_router, config_router

# Load environment variables
load_dotenv()

app = FastAPI(
    title="TradingAgents API",
    description="API for TradingAgents Multi-Agent Trading Framework",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://localhost:3001",
        os.getenv("FRONTEND_URL", "http://localhost:3000"),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(analysis_router)
app.include_router(history_router)
app.include_router(config_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "TradingAgents API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

