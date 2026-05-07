import logging
import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from tradingagents.portfolio.exceptions import PortfolioError
from tradingagents.portfolio.supabase_client import SupabaseClient

logger = logging.getLogger("agent_os")

_API_KEY = os.getenv("AGENT_OS_API_KEY")
_bearer_scheme = HTTPBearer(auto_error=False)

if not _API_KEY:
    logger.warning(
        "AGENT_OS_API_KEY is not set — all requests will be accepted without authentication. "
        "Set this env variable to enable API key gating."
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, str]:
    """V1 (Single Tenant): Gate on a static API key from env.

    If AGENT_OS_API_KEY is not configured, all callers are accepted (dev mode).
    V2 (Multi-Tenant): Decode the JWT using supabase-py and return auth.uid().
    """
    if _API_KEY:
        if credentials is None or credentials.credentials != _API_KEY:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return {"user_id": "tenant_001", "role": "admin"}


def get_db_client() -> SupabaseClient:
    try:
        return SupabaseClient.get_instance()
    except PortfolioError as e:
        logger.exception("Database client initialization failed")
        raise HTTPException(status_code=503, detail="Database unavailable") from e
