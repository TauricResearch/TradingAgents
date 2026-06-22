from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ConfigDict, Field

from tradingagents.batch.adapters import BaseBatchAdapter
from tradingagents.batch.manifest import BatchManifest, BatchRequest, BatchRunState

try:
    from langchain_anthropic.chat_models import convert_to_anthropic_tool
except ImportError:  # pragma: no cover - dependency is present in this repo
    convert_to_anthropic_tool = None


class BatchRequestDeferred(RuntimeError):
    def __init__(self, custom_id: str):
        super().__init__(f"batch request {custom_id} is waiting for provider results")
        self.custom_id = custom_id


class BatchRequestFailed(RuntimeError):
    pass


class BatchRuntimeContext:
    def __init__(
        self,
        *,
        manifest: BatchManifest,
        adapter: BaseBatchAdapter,
        batch_root: Path,
    ):
        self.manifest = manifest
        self.adapter = adapter
        self.batch_root = batch_root
        self.current_run: BatchRunState | None = None
        self.current_node: str | None = None
        self.call_cursor = 0

    def begin_node(self, run: BatchRunState, node: str) -> None:
        self.current_run = run
        self.current_node = node
        self.call_cursor = 0
        progress = run.progress
        if progress.get("active_node") is None:
            progress["active_node"] = node
            progress["active_call_requests"] = []
        elif progress.get("active_node") != node:
            raise RuntimeError(
                f"cannot resume node {node}; run is waiting in {progress.get('active_node')}"
            )

    def end_node(self) -> None:
        if self.current_run is not None:
            self.current_run.progress["active_node"] = None
            self.current_run.progress["active_call_requests"] = []
            self.current_run.status = "running"
        self.current_run = None
        self.current_node = None
        self.call_cursor = 0

    def request_message(
        self,
        *,
        provider: str,
        model: str,
        messages: list[BaseMessage],
        request_kwargs: dict[str, Any],
    ) -> AIMessage:
        response = self._request(
            provider=provider,
            model=model,
            messages=messages,
            request_kwargs=request_kwargs,
            kind="message",
            schema_name=None,
        )
        return self.adapter.message_from_response(response)

    def request_structured(
        self,
        *,
        provider: str,
        model: str,
        messages: list[BaseMessage],
        request_kwargs: dict[str, Any],
        schema: type,
    ) -> Any:
        response = self._request(
            provider=provider,
            model=model,
            messages=messages,
            request_kwargs={**request_kwargs, **structured_kwargs(provider, schema)},
            kind="structured",
            schema_name=schema.__name__,
        )
        return schema(**self.adapter.structured_args_from_response(response))

    def _request(
        self,
        *,
        provider: str,
        model: str,
        messages: list[BaseMessage],
        request_kwargs: dict[str, Any],
        kind: str,
        schema_name: str | None,
    ) -> dict[str, Any]:
        if self.current_run is None or self.current_node is None:
            raise RuntimeError("batch runtime has no active run/node")

        progress = self.current_run.progress
        active_requests = progress.setdefault("active_call_requests", [])
        call_index = self.call_cursor
        if call_index < len(active_requests):
            custom_id = active_requests[call_index]
            request = self.manifest.requests[custom_id]
        else:
            custom_id = self._custom_id(self.current_run.ticker, self.current_node, call_index)
            payload = self.adapter.build_payload(
                model=model,
                messages=messages,
                request_kwargs=request_kwargs,
            )
            request = BatchRequest(
                custom_id=custom_id,
                provider=provider,
                model=model,
                ticker=self.current_run.ticker,
                node=self.current_node,
                call_index=call_index,
                kind=kind,
                payload=self.adapter.line_for_request(custom_id, payload),
                schema_name=schema_name,
            )
            self.manifest.requests[custom_id] = request
            active_requests.append(custom_id)

        if request.status == "succeeded" and request.response is not None:
            self.call_cursor += 1
            return request.response

        if request.status in {"errored", "expired", "canceled"}:
            raise BatchRequestFailed(f"{custom_id} failed: {request.error}")

        self.current_run.status = "waiting"
        raise BatchRequestDeferred(custom_id)

    def _custom_id(self, ticker: str, node: str, call_index: int) -> str:
        raw = f"{self.manifest.run_id}:{ticker}:{node}:{call_index}:{len(self.manifest.requests)}"
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        ticker_part = "".join(ch if ch.isalnum() else "_" for ch in ticker)[:12]
        return f"ta_{ticker_part}_{digest}"


class DeferredBatchChatModel(BaseChatModel):
    provider: str
    model_name: str
    context: BatchRuntimeContext = Field(exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return f"{self.provider}-batch-deferred"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        request_kwargs = dict(kwargs)
        if stop is not None:
            request_kwargs["stop"] = stop
        message = self.context.request_message(
            provider=self.provider,
            model=self.model_name,
            messages=messages,
            request_kwargs=request_kwargs,
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools, *, tool_choice=None, **kwargs) -> Runnable:
        request_kwargs = dict(kwargs)
        if self.provider == "openai":
            request_kwargs["tools"] = [convert_to_openai_tool(tool) for tool in tools]
            if tool_choice is not None:
                request_kwargs["tool_choice"] = tool_choice
        elif self.provider == "anthropic":
            if convert_to_anthropic_tool is None:
                raise RuntimeError("langchain-anthropic tool conversion is unavailable")
            request_kwargs["tools"] = [convert_to_anthropic_tool(tool) for tool in tools]
            if tool_choice is not None:
                request_kwargs["tool_choice"] = tool_choice
        else:
            raise RuntimeError(f"batch deferred model does not support {self.provider}")
        return self.bind(**request_kwargs)

    def with_structured_output(self, schema, *, method=None, **kwargs):
        return DeferredStructuredRunnable(self, schema, kwargs)


class DeferredStructuredRunnable:
    def __init__(
        self,
        llm: DeferredBatchChatModel,
        schema: type,
        request_kwargs: dict[str, Any] | None = None,
    ):
        self.llm = llm
        self.schema = schema
        self.request_kwargs = request_kwargs or {}

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        messages = self.llm._convert_input(input).to_messages()
        request_kwargs = {**self.request_kwargs, **kwargs}
        return self.llm.context.request_structured(
            provider=self.llm.provider,
            model=self.llm.model_name,
            messages=messages,
            request_kwargs=request_kwargs,
            schema=self.schema,
        )


def structured_kwargs(provider: str, schema: type) -> dict[str, Any]:
    if provider == "openai":
        tool = convert_to_openai_tool(schema)
        return {
            "tools": [tool],
            "tool_choice": {"type": "function", "function": {"name": schema.__name__}},
            "parallel_tool_calls": False,
        }
    if provider == "anthropic":
        if convert_to_anthropic_tool is None:
            raise RuntimeError("langchain-anthropic tool conversion is unavailable")
        return {
            "tools": [convert_to_anthropic_tool(schema)],
            "tool_choice": {"type": "tool", "name": schema.__name__},
        }
    raise RuntimeError(f"structured batch output does not support {provider}")
