import logging
import os
from functools import lru_cache

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from tradingagents.portfolio.exceptions import PortfolioError
from tradingagents.portfolio.supabase_client import SupabaseClient

logger = logging.getLogger("agent_os")

_bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _get_api_key() -> str | None:
    """Lazily read the API key from the environment.

    Using lru_cache means the env var is read once on first call (not at import
    time), which allows tests to set os.environ["AGENT_OS_API_KEY"] after import
    without needing to reload the module.  Call ``_get_api_key.cache_clear()`` in
    tests that need to change the value between invocations.
    """
    key = os.getenv("AGENT_OS_API_KEY")
    if not key:
        logger.warning(
            "AGENT_OS_API_KEY is not set — all requests will be accepted without authentication. "
            "Set this env variable to enable API key gating."
        )
    return key


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, str]:
    """V1 (Single Tenant): Gate on a static API key from env.

    If AGENT_OS_API_KEY is not configured, all callers are accepted (dev mode).
    V2 (Multi-Tenant): Decode the JWT using supabase-py and return auth.uid().
    """
    api_key = _get_api_key()
    if api_key and (credentials is None or credentials.credentials != api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return {"user_id": "tenant_001", "role": "admin"}
    return {"user_id": "tenant_001", "role": "admin"}


def get_db_client() -> SupabaseClient:
    try:
        return SupabaseClient.get_instance()
    except PortfolioError as e:
        logger.exception("Database client initialization failed")
        raise HTTPException(status_code=503, detail="Database unavailable") from e
