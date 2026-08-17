from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "TradingAgents Terminal"
    app_env: str = "local"
    secret_key: str = Field(default="change-me-in-production", alias="APP_SECRET_KEY")
    access_token_expire_minutes: int = 60 * 24 * 7
    database_url: str = Field(default=f"sqlite:///{ROOT / 'data' / 'terminal.db'}")
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    default_admin_email: str = "admin@local"
    default_admin_password: str = "admin123"
    default_admin_name: str = "Local Admin"
    analysis_concurrency: int = 1
    market_data_provider: str = "yahoo"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
