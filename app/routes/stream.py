"""
GET /stream/{run_id}?token=<signed> — live SSE feed for one analysis run.

Auth model: query-param HMAC-signed token (see app/services/stream_token.py).
Browser EventSource API can't send custom headers, so the standard
service-to-service HMAC header pattern (app/auth.py) doesn't apply.
The Node side mints a short-lived token bound to the runId.

Wire format: text/event-stream with `data: <json>\\n\\n` records.
Each record is one event from the LangChain callback handler:
- `{"type": "run_started", ...}`
- `{"type": "agent_started", "agent": "...", ...}`
- `{"type": "agent_finished", "agent": "...", "content": "...", ...}`
- `{"type": "agent_error", ...}`
- `{"type": "run_complete", "decision": "...", ...}`
- `{"type": "run_error", ...}`

The stream closes when the runner publishes DONE_SENTINEL on the
underlying Redis channel (handled inside `subscribe_events`).

HMAC auth middleware skips this path (it's GET, not POST). The token
query param is the auth.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.services.pubsub import subscribe_events
from app.services.stream_token import TokenError, verify


logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/stream/{run_id}")
async def stream(run_id: str, token: str = Query(..., description="HMAC-signed access token")):
    """
    Subscribe to a run's progress events via Server-Sent Events.

    Returns 401 on invalid/expired/mismatched token. Otherwise streams
    `text/event-stream` events as the LangChain callback publishes them.
    """
    try:
        verify(token, expected_run_id=run_id)
    except TokenError as e:
        # Don't reveal which check failed (signature vs expiry vs runId)
        # to clients — just 401. Server logs have the reason for ops.
        logger.warning("stream-token rejected for run %s: %s", run_id, e)
        return StreamingResponse(
            iter([_sse_record({"type": "error", "error": "unauthorized"})]),
            status_code=401,
            media_type="text/event-stream",
        )

    async def event_generator():
        # Initial comment-line keeps proxies that buffer until first byte
        # from holding the connection. EventSource ignores comment lines.
        yield b": connected\n\n"
        async for raw in subscribe_events(run_id):
            # raw is the JSON string published by RunRecorderHandler /
            # run_analysis. Forward verbatim — the consumer JSON-decodes.
            yield f"data: {raw}\n\n".encode("utf-8")
        # Channel closed (DONE_SENTINEL received).
        yield b"event: close\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            # Disable buffering on intermediate proxies (nginx, Cloudflare).
            "Cache-Control":          "no-cache",
            "X-Accel-Buffering":      "no",
            "Connection":             "keep-alive",
        },
    )


def _sse_record(payload: dict) -> bytes:
    """Format a one-off JSON payload as a single SSE record."""
    import json
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")
