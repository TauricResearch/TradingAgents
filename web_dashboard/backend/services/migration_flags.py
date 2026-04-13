from __future__ import annotations

import os
from dataclasses import dataclass


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MigrationFlags:
    """Feature flags for backend application-service migration."""

    use_application_services: bool = False
    use_result_store: bool = False
    use_request_context: bool = True


def load_migration_flags() -> MigrationFlags:
    """Load service migration flags from the environment."""
    return MigrationFlags(
        use_application_services=_env_flag("TRADINGAGENTS_USE_APPLICATION_SERVICES", default=False),
        use_result_store=_env_flag("TRADINGAGENTS_USE_RESULT_STORE", default=False),
        use_request_context=_env_flag("TRADINGAGENTS_USE_REQUEST_CONTEXT", default=True),
    )
