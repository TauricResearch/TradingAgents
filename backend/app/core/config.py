import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

def _int_env(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is not None and val.strip():
        try:
            return int(val.strip())
        except ValueError:
            return default
    return default

class Settings:
    PROJECT_NAME: str = "TradingAgents Pro Web API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    PROJECT_ROOT: Path = PROJECT_ROOT

    # Storage
    DATA_DIR: Path = DATA_DIR
    DB_PATH: Path = DATA_DIR / "tradingagents.db"
    REPORTS_DIR: Path = PROJECT_ROOT / "results" / "reports"

    # Concurrency
    MAX_CONCURRENT_JOBS: int = _int_env("TRADINGAGENTS_MAX_CONCURRENT_JOBS", 4)

    # Cache
    CACHE_DIR: Path = DATA_DIR / "cache"
    CACHE_TTL_HOURS: int = _int_env("TRADINGAGENTS_CACHE_TTL_HOURS", 12)

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

    # Authentication & Security
    SESSION_COOKIE_NAME: str = "tradingagents_session"
    SESSION_EXPIRE_DAYS: int = _int_env("SESSION_EXPIRE_DAYS", 7)
    ADMIN_USERNAME: str = os.getenv("TRADINGAGENTS_ADMIN_USER") or "admin"
    ADMIN_INITIAL_PASSWORD: str = os.getenv("TRADINGAGENTS_ADMIN_PASSWORD") or "TradingAgents@2024"
    MAX_LOGIN_ATTEMPTS: int = _int_env("MAX_LOGIN_ATTEMPTS", 5)
    LOCKOUT_MINUTES: int = _int_env("LOCKOUT_MINUTES", 15)
    SECURE_COOKIES: bool = os.getenv("SECURE_COOKIES", "false").lower() in ("true", "1", "yes")

settings = Settings()
settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
