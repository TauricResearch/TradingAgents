"""Chat with a completed run.

Two endpoints per run:
- GET /runs/{run_id}/chat       -> message history (persisted in SQLite)
- WS  /runs/{run_id}/chat/stream -> ask a question, stream the answer

WebSocket protocol:
    Client sends a JSON line: {"question": "..."}
    Server sends:
        {"type": "delta", "text": "...partial..."}   (many)
        {"type": "done", "model": "...", "content": "...full..."}
        {"type": "error", "message": "..."}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from gui import chat as chat_mod
from gui import storage
from gui.log_browser import load_archive_full, load_log
from service.schemas import ChatMessage

router = APIRouter(prefix="/runs", tags=["chat"])


@router.get("/{run_id}/chat", response_model=List[ChatMessage])
def list_messages(run_id: str) -> List[ChatMessage]:
    rows = storage.list_chat_messages(run_id)
    return [ChatMessage(**r) for r in rows]


@router.delete("/{run_id}/chat")
def clear_chat(run_id: str) -> dict:
    storage.clear_chat(run_id)
    return {"cleared": True}


@router.websocket("/{run_id}/chat/stream")
async def stream_chat(ws: WebSocket, run_id: str) -> None:
    await ws.accept()
    try:
        first = await ws.receive_text()
        msg = json.loads(first)
        question = (msg or {}).get("question", "").strip()
        if not question:
            await ws.send_text(json.dumps({"type": "error", "message": "empty question"}))
            return

        row = storage.get_run(run_id)
        if not row:
            await ws.send_text(json.dumps({"type": "error", "message": "unknown run"}))
            return
        log_path = row.get("log_path")
        if not log_path or not Path(log_path).exists():
            await ws.send_text(json.dumps({"type": "error", "message": "run has no transcript yet"}))
            return

        state = load_log(log_path) or {}
        full = load_archive_full(log_path) or {}
        tool_trace = full.get("tool_trace") or []
        meta = {
            "ticker": row["ticker"],
            "trade_date": row["trade_date"],
            "decision": row.get("decision"),
            "provider": row.get("provider"),
            "deep_model": row.get("deep_model"),
            "quick_model": row.get("quick_model"),
            "started_at": row.get("started_at"),
            "completed_at": row.get("completed_at"),
            "run_id": run_id,
        }

        # Persist the user's question first.
        storage.add_chat_message(run_id=run_id, role="user", content=question)
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in storage.list_chat_messages(run_id)
            if m["role"] in ("user", "assistant")
        ][:-1]  # exclude the just-added question

        # Stream the answer.
        full_text = ""
        try:
            for chunk in chat_mod.stream_response(state, meta, history, question, tool_trace=tool_trace):
                full_text += chunk
                await ws.send_text(json.dumps({"type": "delta", "text": chunk}))
        except Exception as e:
            await ws.send_text(json.dumps({"type": "error", "message": str(e)}))
            return

        model_label = chat_mod.quick_think_label()
        storage.add_chat_message(run_id=run_id, role="assistant", content=full_text, model=model_label)
        await ws.send_text(json.dumps({"type": "done", "model": model_label, "content": full_text}))
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await ws.close()
        except RuntimeError:
            pass
