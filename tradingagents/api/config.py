"""
Configuration settings for the FastAPI backend.

Loads settings from environment variables using pydantic-settings.
"""

import secrets
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow"
    )

    # JWT Configuration
    JWT_SECRET_KEY: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Secret key for JWT token signing"
    )
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="Algorithm for JWT token signing"
    )
    JWT_EXPIRATION_MINUTES: int = Field(
        default=30,
        description="JWT token expiration time in minutes"
    )

    # Database Configuration
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./tradingagents.db",
        description="Database connection URL"
    )

    # CORS Configuration
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins"
    )

    # API Configuration
    API_V1_PREFIX: str = Field(
        default="/api/v1",
        description="API v1 prefix"
    )

    # Environment
    ENVIRONMENT: str = Field(
        default="development",
        description="Environment (development/production)"
    )

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret_key(cls, v: str) -> str:
        """Validate JWT secret key has minimum length."""
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def validate_jwt_algorithm(cls, v: str) -> str:
        """Validate JWT algorithm is supported."""
        allowed = ["HS256", "HS384", "HS512"]
        if v not in allowed:
            raise ValueError(f"JWT_ALGORITHM must be one of {allowed}")
        return v

    @field_validator("JWT_EXPIRATION_MINUTES")
    @classmethod
    def validate_jwt_expiration(cls, v: int) -> int:
        """Validate JWT expiration is positive."""
        if v <= 0:
            raise ValueError("JWT_EXPIRATION_MINUTES must be positive")
        return v


# Global settings instance (created at import time)
# In tests, set environment variables BEFORE importing this module
try:
    settings = Settings()
except Exception:
    # If validation fails (e.g., in test setup), create with defaults
    # Tests should mock environment variables before importing
    settings = None  # type: ignore


def get_settings() -> Settings:
    """Get settings instance."""
    global settings
    if settings is None:
        settings = Settings()
    return settings
