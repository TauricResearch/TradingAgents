from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    DB_USER: str
    DB_PASSWORD: str
    WALLET_PASSWORD: str
    DB_DSN: str
    SECRET_KEY: str

@lru_cache 
def get_settings():
    return Settings()