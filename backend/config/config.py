from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # MySQL 데이터베이스 설정
    DB_HOST: str 
    DB_PORT: int 
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    SECRET_KEY: str

@lru_cache 
def get_settings():
    return Settings()