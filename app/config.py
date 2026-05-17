"""
Service-layer env-var loading via pydantic-settings.

Required vars fail-fast at import time with a bullet-list error message —
better than discovering a missing var mid-request. Optional vars carry
defaults that match the production deploy on Railway.

Treat this file as a python-temp-pro template: app-specific vars belong
elsewhere (or in a sibling settings class), not here.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Service-wide configuration. Reads from process environment (.env in
    local dev via the SettingsConfigDict below).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        # Allow unrelated env vars (TRADINGAGENTS_*, GOOGLE_API_KEY, etc.) to
        # coexist without pydantic raising. The upstream library reads its
        # own env vars directly.
        extra="ignore",
    )

    # ── Required ──────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        ...,
        description="Neon Postgres pooled connection URL. Shared with the Node lyceum-fund app.",
    )
    REDIS_URL: str = Field(
        ...,
        description="Upstash Redis URL. Shared with the Node side for pub-sub / SSE.",
    )
    OPENAI_API_KEY: str = Field(
        ...,
        description="OpenAI key used by TradingAgents' default LLM provider.",
    )
    HMAC_SHARED_SECRET: str = Field(
        ...,
        description="HMAC-SHA256 secret. The Node-side worker signs requests; we verify.",
    )

    # ── Optional ──────────────────────────────────────────────────────────
    DIRECT_URL: str | None = Field(
        default=None,
        description="Neon Postgres direct (non-pooled) URL. Used by Alembic migrations.",
    )
    SENTRY_DSN: str | None = Field(
        default=None,
        description="If set, errors flow to the shared Sentry project. See observability.py.",
    )
    APP_SLUG: str = Field(
        default="unknown",
        description="Slug of the spawned app this service backs. Sentry events tagged with `app:<slug>`.",
    )
    NODE_ENV: str = Field(
        default="development",
        description="Mirrors the Node ecosystem convention. 'production' enables stricter defaults.",
    )
    PORT: int = Field(
        default=8000,
        description="Bind port. Railway injects this automatically.",
    )
    CORS_ALLOW_ORIGINS: str | None = Field(
        default=None,
        description=(
            "Comma-separated list of origins allowed to call /stream/{run_id} "
            "from the browser. Required for SSE — EventSource enforces CORS. "
            "Defaults in main.py cover the prod Vercel URL + localhost; override "
            "here when you add custom domains or need Vercel preview URLs."
        ),
    )


# Module-level singleton — import as `from app.config import settings`.
settings = Settings()  # type: ignore[call-arg]
