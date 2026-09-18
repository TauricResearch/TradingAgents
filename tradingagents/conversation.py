"""File exchange between a running graph and an assistant in the current chat.

No model endpoint or credential is used here. A responder must actively read
each request and submit an answer; this module does not launch another agent.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr


class ConversationBridgeError(RuntimeError):
    """Abort the conversation run without retrying through another provider."""


class ConversationTimeoutError(ConversationBridgeError, TimeoutError):
    pass


class ConversationCancelledError(ConversationBridgeError):
    pass


class ConversationToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: StrictStr = Field(min_length=1)
    name: StrictStr = Field(min_length=1)
    args: dict[str, Any]


class ConversationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: StrictStr
    content: StrictStr = ""
    tool_calls: list[ConversationToolCall] = Field(default_factory=list)
    cancel: StrictBool = False


def conversation_directory() -> Path:
    return (
        Path(os.environ.get("TRADINGAGENTS_CONVERSATION_DIR") or ".tradingagents/conversation")
        .expanduser()
        .resolve()
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def publish_json(path: Path, value: dict) -> None:
    """Publish a complete private file atomically, refusing to overwrite it."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        # Unlike replace(), link() cannot silently replace an earlier answer.
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def request_path(directory: Path, request_id: str) -> Path:
    if not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id):
        raise ValueError("request_id must be the 32-character ID from a pending request")
    return directory / request_id / "request.json"


def pending_requests(directory: Path) -> list[dict]:
    pending = []
    for path in sorted(directory.glob("*/request.json")):
        if (path.parent / "done.json").exists() or (path.parent / "response.json").exists():
            continue
        request = read_json(path)
        if request["expires_at"] > time.time():
            pending.append(request)
    return sorted(pending, key=lambda request: request["created_at"])


def validate_response(request: dict, value: dict) -> AIMessage:
    response = ConversationResponse.model_validate(value)
    if response.request_id != request["request_id"]:
        raise ValueError("Response request_id does not match the pending request")
    if response.cancel:
        raise ConversationCancelledError("Conversation request cancelled by responder")
    if not response.content.strip() and not response.tool_calls:
        raise ValueError("An answer needs content or tool_calls")
    allowed = {tool["function"]["name"] for tool in request["tools"]}
    ids = set()
    for call in response.tool_calls:
        if call.name not in allowed:
            raise ValueError(f"Tool {call.name!r} is not offered by this request")
        if call.id in ids:
            raise ValueError("Tool call IDs must be unique within a response")
        ids.add(call.id)
    choice = request.get("tool_choice")
    if choice in ("any", "required") and not response.tool_calls:
        raise ValueError("This request requires a tool call (including schema output)")
    if choice == "none" and response.tool_calls:
        raise ValueError("This request does not allow tool calls")
    named = choice.get("function", {}).get("name") if isinstance(choice, dict) else choice
    if named in allowed and (
        not response.tool_calls or any(call.name != named for call in response.tool_calls)
    ):
        raise ValueError(f"This request requires the {named!r} tool")
    return AIMessage(
        content=response.content,
        tool_calls=[call.model_dump() for call in response.tool_calls],
        response_metadata={"provider": "conversation", "request_id": response.request_id},
    )


def submit_response(directory: Path, value: dict) -> Path:
    """Validate before publishing so a typo can be corrected without a new run."""
    path = request_path(directory, value.get("request_id", ""))
    request = read_json(path)
    if (path.parent / "done.json").exists() or time.time() >= request["expires_at"]:
        raise ValueError("Request has completed, expired, or been cancelled")
    # A validated cancellation uses the same one-answer-only channel.
    with suppress(ConversationCancelledError):
        validate_response(request, value)
    target = path.parent / "response.json"
    publish_json(target, value)
    return target
