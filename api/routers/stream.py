import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from api.auth import _resolve_identity_from_auth_service, enforce_quota
from api.scheduler import redis_client

logger = logging.getLogger("pulse-trading-signals-service")
router = APIRouter(tags=["stream"])


@router.get("/signals-ms/stream")
async def sse_stream(
    request: Request,
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
):
    jwt_token = None
    if authorization and authorization.startswith("Bearer "):
        jwt_token = authorization[7:]
    elif token:
        jwt_token = token

    if not jwt_token:
        raise HTTPException(status_code=401, detail="Authentication token required")

    user_id, tier = await _resolve_identity_from_auth_service(jwt_token)
    entitlement = enforce_quota(user_id, tier, log_view=False)

    if entitlement.locked:

        async def _exhausted():
            yield f"event: quota_exhausted\ndata: {json.dumps({'locked': True, 'tier': entitlement.tier})}\n\n"

        return StreamingResponse(_exhausted(), media_type="text/event-stream")

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("pulse:trading_signals")

    async def _events():
        last_heartbeat = time.time()
        try:
            yield "event: connection\ndata: Connected to real-time signals stream\n\n"

            while True:
                if await request.is_disconnected():
                    break

                try:
                    msg = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                    if msg:
                        signal = json.loads(msg["data"])

                        if tier == "free":
                            current = enforce_quota(user_id, tier, log_view=False)
                            if current.locked:
                                yield f"event: quota_exhausted\ndata: {json.dumps({'locked': True})}\n\n"
                                break
                            yield f"event: signal\ndata: {json.dumps(signal)}\n\n"
                            current = enforce_quota(user_id, tier, log_view=True)
                            if current.locked:
                                yield f"event: quota_exhausted\ndata: {json.dumps({'locked': True})}\n\n"
                                break
                        else:
                            yield f"event: signal\ndata: {json.dumps(signal)}\n\n"
                    else:
                        if time.time() - last_heartbeat > 20:
                            yield "event: heartbeat\ndata: ping\n\n"
                            last_heartbeat = time.time()
                except Exception as e:
                    logger.error("SSE stream error: %s", e)
                    yield "event: error\ndata: Stream error\n\n"
                    break
        finally:
            await pubsub.unsubscribe("pulse:trading_signals")
            await pubsub.close()

    return StreamingResponse(_events(), media_type="text/event-stream")
