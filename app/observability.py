"""
Sentry initialisation for the FastAPI service.

Gated on SENTRY_DSN — absent → no-op so local dev without a DSN works
unchanged. When configured, every event picks up an `app:<slug>` tag so
the shared `two-trees-shared-python` Sentry project is filterable per
spawned app (mirrors the Node-side pattern from TT-275).

Treat this as a python-temp-pro template file. No trading-specific
references — only generic Python-service instrumentation.
"""

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.config import settings


def init_sentry() -> None:
    """
    Initialise Sentry if SENTRY_DSN is configured. Idempotent — safe to
    call once at startup; subsequent calls become no-ops because Sentry's
    client init already happened.
    """
    if not settings.SENTRY_DSN:
        return

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.NODE_ENV,
        # Lower sample rate in prod — tracing every request gets expensive
        # under sustained load. 1.0 in dev for full visibility.
        traces_sample_rate=0.2 if settings.NODE_ENV == "production" else 1.0,
        integrations=[
            FastApiIntegration(),
            StarletteIntegration(),
            SqlalchemyIntegration(),
        ],
        # If Railway injects RAILWAY_GIT_COMMIT_SHA we'd tag releases with it,
        # but Sentry SDK reads that automatically when present — no manual
        # release= needed.
    )

    # Every event gets `app:<slug>` — enables Sentry's tag-filter UI to
    # isolate events by spawned-app slug in the shared project.
    sentry_sdk.set_tag("app", settings.APP_SLUG)
