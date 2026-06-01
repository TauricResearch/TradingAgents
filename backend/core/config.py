from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from cryptography.fernet import Fernet

# Always resolve .env from the project root, regardless of CWD
_ROOT_ENV = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ROOT_ENV), env_file_encoding="utf-8", extra="ignore")

    # Auth
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: str = ""  # bcrypt hash, set via init script

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://tradingagents:tradingagents@localhost:5432/tradingagents"

    # Encryption for broker credentials
    ENCRYPTION_KEY: str = ""  # Fernet key; auto-generated if empty

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    def get_fernet(self) -> Fernet:
        key = self.ENCRYPTION_KEY
        if not key:
            raise RuntimeError("ENCRYPTION_KEY is not set in .env")
        return Fernet(key.encode() if isinstance(key, str) else key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
