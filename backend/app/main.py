import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env variables into environment
load_dotenv(find_dotenv(usecwd=True), override=True)
load_dotenv(PROJECT_ROOT / ".env", override=True)


from .api.v1.config import router as config_router  # noqa: E402
from .api.v1.jobs import router as jobs_router  # noqa: E402
from .api.v1.memory import router as memory_router  # noqa: E402
from .api.v1.reports import router as reports_router  # noqa: E402
from .core.cache import market_cache  # noqa: E402
from .core.config import settings  # noqa: E402
from .core.database import db  # noqa: E402
from .workers.job_manager import job_manager  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db._init_db()
    market_cache.cleanup_expired()
    yield
    # Shutdown
    job_manager.executor.shutdown(wait=False)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Asynchronous Backend & Multi-Job Coordinator for TradingAgents",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API v1 Routers
api_v1_prefix = settings.API_V1_STR
app.include_router(jobs_router, prefix=api_v1_prefix)
app.include_router(reports_router, prefix=api_v1_prefix)
app.include_router(config_router, prefix=api_v1_prefix)
app.include_router(memory_router, prefix=api_v1_prefix)

@app.get("/health")
@app.get(f"{api_v1_prefix}/health")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "max_concurrent_workers": settings.MAX_CONCURRENT_JOBS
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
