import datetime
import hashlib
import json
import logging
import urllib.error as _ue
import urllib.request as _ur

import jwt
from fastapi import HTTPException, Request

from api.config import (
    AUTH_SERVICE_URL,
    DEV_BYPASS_AUTH,
    FREE_TIER_QUOTA_LIMIT,
    JWT_ALGORITHM,
    JWT_SECRET,
)
from api.database import get_db_connection
from api.models import EntitlementBlock

logger = logging.getLogger("pulse-trading-signals-service")

# Lazy import to avoid circular import at module level
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis
        from api.config import REDIS_URL

        _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


async def _resolve_identity_from_auth_service(token: str) -> tuple[str, str]:
    if DEV_BYPASS_AUTH in ("pro", "free"):
        logger.warning(
            "DEV_BYPASS_AUTH active — skipping auth service (development only)"
        )
        payload = jwt.decode(token, options={"verify_signature": False})
        return str(payload.get("sub") or "dev-user"), DEV_BYPASS_AUTH

    cache_key = f"identity:{hashlib.sha256(token.encode()).hexdigest()}"
    try:
        cached = await _get_redis().get(cache_key)
        if cached:
            user_id, tier = cached.split(":", 1)
            return user_id, tier
    except Exception:
        pass

    try:
        req = _ur.Request(
            f"{AUTH_SERVICE_URL}/auth-ms/me/entitlements",
            headers={"Authorization": f"Bearer {token}"},
        )
        with _ur.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        tier = "pro" if data.get("is_pro") else "free"
    except _ue.HTTPError as e:
        if e.code == 401:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        raise HTTPException(status_code=503, detail="Auth service unavailable")
    except Exception:
        raise HTTPException(status_code=503, detail="Auth service unavailable")

    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        user_id = str(payload.get("sub") or payload.get("user_id") or "")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID missing from token")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Malformed token")

    try:
        await _get_redis().setex(cache_key, 60, f"{user_id}:{tier}")
    except Exception:
        pass

    return user_id, tier


async def get_user_claims_async(request: Request) -> tuple[str, str]:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")
    return await _resolve_identity_from_auth_service(auth[7:])


def get_user_claims(request: Request) -> tuple[str, str]:
    """Sync fallback for SSE path — does not resolve tier from auth service."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return "anonymous", "free"
    try:
        payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return str(payload.get("sub") or "anonymous"), "free"
    except Exception:
        return "anonymous", "free"


def enforce_quota(user_id: str, tier: str, log_view: bool = False) -> EntitlementBlock:
    if tier == "pro":
        return EntitlementBlock(tier="pro", remaining_views=999999, locked=False)

    limit = FREE_TIER_QUOTA_LIMIT
    now = datetime.datetime.now()
    window_start = now - datetime.timedelta(hours=24)

    conn = get_db_connection()
    try:
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM user_quota_logs WHERE user_id = ? AND viewed_at >= ?",
            (user_id, window_start.strftime("%Y-%m-%d %H:%M:%S")),
        ).fetchone()["cnt"]

        oldest = conn.execute(
            "SELECT viewed_at FROM user_quota_logs WHERE user_id = ? AND viewed_at >= ? ORDER BY viewed_at ASC LIMIT 1",
            (user_id, window_start.strftime("%Y-%m-%d %H:%M:%S")),
        ).fetchone()

        reset_at = None
        if oldest:
            oldest_time = datetime.datetime.strptime(
                oldest["viewed_at"], "%Y-%m-%d %H:%M:%S"
            )
            reset_at = oldest_time + datetime.timedelta(hours=24)

        locked = count >= limit

        if not locked and log_view:
            conn.execute(
                "INSERT INTO user_quota_logs (user_id, viewed_at) VALUES (?, ?)",
                (user_id, now.strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
            count += 1
            locked = count >= limit

        return EntitlementBlock(
            tier="free",
            remaining_views=max(0, limit - count),
            reset_at=reset_at,
            locked=locked,
            cooldown_ends_at=reset_at if locked else None,
        )
    finally:
        conn.close()
