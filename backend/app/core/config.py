import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

class Settings:
    PROJECT_NAME: str = "TradingAgents Pro Web API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Storage
    DATA_DIR: Path = DATA_DIR
    DB_PATH: Path = DATA_DIR / "tradingagents.db"
    REPORTS_DIR: Path = PROJECT_ROOT / "results" / "reports"

    # Concurrency
    MAX_CONCURRENT_JOBS: int = int(os.getenv("TRADINGAGENTS_MAX_CONCURRENT_JOBS", "4"))

    # Cache
    CACHE_DIR: Path = DATA_DIR / "cache"
    CACHE_TTL_HOURS: int = int(os.getenv("TRADINGAGENTS_CACHE_TTL_HOURS", "12"))

    # CORS
    _cors_env: str | None = os.getenv("CORS_ORIGINS")
    CORS_ORIGINS: list[str] = (
        [o.strip() for o in _cors_env.split(",") if o.strip()]
        if _cors_env
        else [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )

settings = Settings()
settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
