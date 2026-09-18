"""LangChain model whose answers are supplied through the current conversation."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, messages_to_dict
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

from tradingagents.conversation import (
    ConversationBridgeError,
    ConversationCancelledError,
    ConversationTimeoutError,
    conversation_directory,
    publish_json,
    read_json,
    validate_response,
)

from .base_client import BaseLLMClient


class ConversationChatModel(BaseChatModel):
    directory: Path = Field(default_factory=conversation_directory)
    timeout_seconds: float = Field(default=1800, gt=0, allow_inf_nan=False)
    poll_seconds: float = Field(default=0.25, gt=0, allow_inf_nan=False)
    # This is a routing label, not the ID of the model running in the chat app.
    model_name: str = "conversation"

    @property
    def _llm_type(self) -> str:
        return "conversation"

    @property
    def _identifying_params(self) -> dict:
        return {"directory": str(self.directory), "model_name": self.model_name}

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        # BaseChatModel.with_structured_output supplies a Pydantic class here.
        # LangChain validates that schema after the response is received.
        return self.bind(
            tools=[convert_to_openai_tool(tool) for tool in tools],
            tool_choice=tool_choice,
            **kwargs,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop=None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        request_id = uuid4().hex
        folder = self.directory.expanduser().resolve() / request_id
        created = time.time()
        metadata = getattr(run_manager, "metadata", None) or {}
        request = {
            "version": 1,
            "request_id": request_id,
            "created_at": created,
            "expires_at": created + self.timeout_seconds,
            "pid": os.getpid(),
            "agent": metadata.get("langgraph_node", "conversation"),
            "messages": messages_to_dict(messages),
            "tools": kwargs.get("tools", []),
            "tool_choice": kwargs.get("tool_choice"),
            "stop": stop,
        }
        publish_json(folder / "request.json", request)
        print(f"CONVERSATION_WAIT {request['agent']} {folder / 'request.json'}", flush=True)
        deadline = time.monotonic() + self.timeout_seconds
        status = "failed"
        try:
            while time.monotonic() < deadline:
                response_path = folder / "response.json"
                if response_path.exists():
                    message = validate_response(request, read_json(response_path))
                    if stop and message.content:
                        cuts = [message.content.find(s) for s in stop if s in message.content]
                        if cuts:
                            message.content = message.content[: min(cuts)]
                    status = "completed"
                    return ChatResult(generations=[ChatGeneration(message=message)])
                time.sleep(self.poll_seconds)
            status = "timed_out"
            raise ConversationTimeoutError(
                f"No conversation response within {self.timeout_seconds:g}s: {request_id}"
            )
        except (KeyboardInterrupt, ConversationCancelledError):
            status = "cancelled"
            raise
        except ConversationBridgeError:
            raise
        except Exception as exc:
            raise ConversationBridgeError(f"Invalid response for {request_id}: {exc}") from exc
        finally:
            publish_json(folder / "done.json", {"status": status, "finished_at": time.time()})


class ConversationClient(BaseLLMClient):
    provider = "conversation"

    def get_llm(self) -> ConversationChatModel:
        timeout = self.kwargs.get("conversation_timeout")
        if timeout is None:
            timeout = float(os.environ.get("TRADINGAGENTS_CONVERSATION_TIMEOUT") or 1800)
        return ConversationChatModel(
            directory=self.kwargs.get("conversation_dir") or conversation_directory(),
            timeout_seconds=timeout,
            callbacks=self.kwargs.get("callbacks"),
            cache=False,
        )

    def validate_model(self) -> bool:
        return True
