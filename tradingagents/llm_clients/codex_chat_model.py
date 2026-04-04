from __future__ import annotations

import json
import threading
import uuid
from typing import Any, Callable, Sequence

from pydantic import ConfigDict, Field, PrivateAttr

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .codex_app_server import CodexAppServerSession, CodexStructuredOutputError
from .codex_message_codec import (
    format_messages_for_codex,
    normalize_input_messages,
    strip_json_fence,
)
from .codex_preflight import run_codex_preflight
from .codex_schema import (
    build_plain_response_schema,
    build_tool_response_schema,
    normalize_tools_for_codex,
)


class CodexChatModel(BaseChatModel):
    """LangChain chat model that talks to `codex app-server` over stdio."""

    model: str
    codex_binary: str | None = None
    codex_reasoning_effort: str | None = None
    codex_summary: str | None = None
    codex_personality: str | None = None
    codex_workspace_dir: str
    codex_request_timeout: float = 120.0
    codex_max_retries: int = 2
    codex_cleanup_threads: bool = True
    session_factory: Callable[..., CodexAppServerSession] | None = Field(
        default=None, exclude=True, repr=False
    )
    preflight_runner: Callable[..., Any] | None = Field(
        default=None, exclude=True, repr=False
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _session: CodexAppServerSession | None = PrivateAttr(default=None)
    _session_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _preflight_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _preflight_done: bool = PrivateAttr(default=False)

    @property
    def _llm_type(self) -> str:
        return "codex"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "codex_binary": self.codex_binary,
            "codex_reasoning_effort": self.codex_reasoning_effort,
            "codex_summary": self.codex_summary,
            "codex_personality": self.codex_personality,
        }

    def preflight(self) -> None:
        with self._preflight_lock:
            if self._preflight_done:
                return
            runner = self.preflight_runner or run_codex_preflight
            runner(
                codex_binary=self.codex_binary,
                model=self.model,
                request_timeout=self.codex_request_timeout,
                workspace_dir=self.codex_workspace_dir,
                cleanup_threads=self.codex_cleanup_threads,
                session_factory=self.session_factory or CodexAppServerSession,
            )
            self._preflight_done = True

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable | Any],
        *,
        tool_choice: str | bool | dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        normalized_tools = normalize_tools_for_codex(tools)
        return self.bind(tools=normalized_tools, tool_choice=tool_choice, **kwargs)

    def close(self) -> None:
        with self._session_lock:
            if self._session is not None:
                self._session.close()
                self._session = None

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        self.preflight()

        normalized_messages = normalize_input_messages(messages)
        tools = kwargs.get("tools") or []
        tool_choice = kwargs.get("tool_choice")
        tool_binding = self._resolve_tool_binding(tools, tool_choice)
        tools = tool_binding["tools"]
        effective_tool_choice = tool_binding["tool_choice"]
        output_schema = tool_binding["output_schema"]
        tool_arguments_as_json_string = tool_binding["tool_arguments_as_json_string"]

        raw_response: str | None = None
        last_error: Exception | None = None
        for attempt in range(self.codex_max_retries + 1):
            retry_message = None
            if attempt:
                previous_error = str(last_error) if last_error is not None else "unknown schema mismatch"
                retry_message = (
                    "The previous response did not satisfy TradingAgents validation: "
                    f"{previous_error}. Return only valid JSON that exactly matches the requested "
                    "schema and tool argument requirements."
                )

            prompt = format_messages_for_codex(
                normalized_messages,
                tool_names=[tool["function"]["name"] for tool in tools],
                tool_schemas=tools,
                tool_choice=effective_tool_choice,
                tool_arguments_as_json_string=tool_arguments_as_json_string,
                retry_message=retry_message,
            )
            result = self._session_or_create().invoke(
                prompt=prompt,
                model=self.model,
                output_schema=output_schema,
                reasoning_effort=self.codex_reasoning_effort,
                summary=self.codex_summary,
                personality=self.codex_personality,
            )
            raw_response = result.final_text

            if run_manager is not None:
                for notification in result.notifications:
                    if notification.get("method") != "item/agentMessage/delta":
                        continue
                    params = notification.get("params", {})
                    if isinstance(params, dict):
                        delta = params.get("delta")
                        if isinstance(delta, str) and delta:
                            run_manager.on_llm_new_token(delta)

            try:
                ai_message = (
                    self._parse_tool_response(
                        raw_response,
                        tools,
                        tool_arguments_as_json_string=tool_arguments_as_json_string,
                    )
                    if tools
                    else self._parse_plain_response(raw_response)
                )
                return ChatResult(generations=[ChatGeneration(message=ai_message)])
            except (json.JSONDecodeError, CodexStructuredOutputError, ValueError) as exc:
                last_error = exc
                continue

        raise CodexStructuredOutputError(
            "Codex returned malformed structured output after "
            f"{self.codex_max_retries + 1} attempt(s): {last_error}. "
            f"Last response: {raw_response!r}"
        )

    def _parse_plain_response(self, raw_response: str) -> AIMessage:
        payload = json.loads(strip_json_fence(raw_response))
        if not isinstance(payload, dict) or not isinstance(payload.get("answer"), str):
            raise CodexStructuredOutputError(
                f"Expected plain response JSON with string `answer`, got: {payload!r}"
            )
        return AIMessage(content=payload["answer"])

    def _parse_tool_response(
        self,
        raw_response: str,
        tools: Sequence[dict[str, Any]],
        *,
        tool_arguments_as_json_string: bool,
    ) -> AIMessage:
        payload = json.loads(strip_json_fence(raw_response))
        if not isinstance(payload, dict):
            raise CodexStructuredOutputError(f"Expected JSON object, got: {payload!r}")

        mode = payload.get("mode")
        content = payload.get("content", "")
        if not isinstance(content, str):
            raise CodexStructuredOutputError("Structured response `content` must be a string.")

        if mode == "final":
            tool_calls = payload.get("tool_calls", [])
            if tool_calls not in ([], None):
                raise CodexStructuredOutputError(
                    f"`mode=final` must not include tool calls, got: {tool_calls!r}"
                )
            return AIMessage(content=content)

        if mode != "tool_calls":
            raise CodexStructuredOutputError(f"Unknown structured response mode: {mode!r}")

        raw_tool_calls = payload.get("tool_calls")
        if not isinstance(raw_tool_calls, list) or not raw_tool_calls:
            raise CodexStructuredOutputError("`mode=tool_calls` requires a non-empty tool_calls array.")

        tool_calls: list[dict[str, Any]] = []
        tool_parameters = {
            tool.get("function", {}).get("name"): tool.get("function", {}).get("parameters", {})
            for tool in tools
        }
        for item in raw_tool_calls:
            if not isinstance(item, dict):
                raise CodexStructuredOutputError(f"Tool call entries must be objects, got: {item!r}")
            name = item.get("name")
            arguments = self._extract_tool_arguments(
                item,
                tool_arguments_as_json_string=tool_arguments_as_json_string,
            )
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise CodexStructuredOutputError(
                    f"Tool call entries must include string name and object arguments, got: {item!r}"
                )
            if name not in tool_parameters:
                raise CodexStructuredOutputError(
                    f"Tool call name '{name}' is not in the bound tool set."
                )
            self._validate_tool_arguments(name, arguments, tool_parameters[name])
            tool_calls.append(
                {
                    "name": name,
                    "args": arguments,
                    "id": f"call_{uuid.uuid4().hex}",
                }
            )

        return AIMessage(content=content, tool_calls=tool_calls)

    def _extract_tool_arguments(
        self,
        item: dict[str, Any],
        *,
        tool_arguments_as_json_string: bool,
    ) -> dict[str, Any]:
        if tool_arguments_as_json_string:
            raw_arguments = item.get("arguments_json")
            if not isinstance(raw_arguments, str):
                raise CodexStructuredOutputError(
                    f"Tool call entries must include string arguments_json, got: {item!r}"
                )
            try:
                parsed = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise CodexStructuredOutputError(
                    f"Tool call arguments_json must contain valid JSON, got: {raw_arguments!r}"
                ) from exc
            if not isinstance(parsed, dict):
                raise CodexStructuredOutputError(
                    f"Tool call arguments_json must decode to an object, got: {parsed!r}"
                )
            return parsed

        arguments = item.get("arguments")
        if not isinstance(arguments, dict):
            raise CodexStructuredOutputError(
                f"Tool call entries must include object arguments, got: {item!r}"
            )
        return arguments

    def _validate_tool_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        schema: dict[str, Any] | None,
    ) -> None:
        if not isinstance(schema, dict):
            return

        properties = schema.get("properties")
        if properties is not None and not isinstance(properties, dict):
            raise CodexStructuredOutputError(
                f"Tool schema for '{tool_name}' has invalid properties metadata."
            )

        required = schema.get("required") or []
        if isinstance(required, list):
            missing = [name for name in required if name not in arguments]
            if missing:
                raise CodexStructuredOutputError(
                    f"Tool call '{tool_name}' is missing required arguments: {', '.join(missing)}"
                )

        if properties and schema.get("additionalProperties") is False:
            unexpected = [name for name in arguments if name not in properties]
            if unexpected:
                raise CodexStructuredOutputError(
                    f"Tool call '{tool_name}' included unexpected arguments: {', '.join(unexpected)}"
                )

    def _session_or_create(self) -> CodexAppServerSession:
        with self._session_lock:
            if self._session is None:
                factory = self.session_factory or CodexAppServerSession
                self._session = factory(
                    codex_binary=self.codex_binary,
                    request_timeout=self.codex_request_timeout,
                    workspace_dir=self.codex_workspace_dir,
                    cleanup_threads=self.codex_cleanup_threads,
                )
                self._session.start()
            return self._session

    def _resolve_tool_binding(
        self,
        tools: Sequence[dict[str, Any]],
        tool_choice: Any,
    ) -> dict[str, Any]:
        tool_list = list(tools)
        if not tool_list:
            return {
                "tools": [],
                "tool_choice": None,
                "output_schema": build_plain_response_schema(),
                "tool_arguments_as_json_string": False,
            }

        if tool_choice in (None, "auto"):
            return {
                "tools": tool_list,
                "tool_choice": None if tool_choice is None else "auto",
                "output_schema": build_tool_response_schema(tool_list, allow_final=True),
                "tool_arguments_as_json_string": len(tool_list) > 1,
            }

        if tool_choice in (False, "none"):
            return {
                "tools": [],
                "tool_choice": "none",
                "output_schema": build_plain_response_schema(),
                "tool_arguments_as_json_string": False,
            }

        if tool_choice in (True, "any", "required"):
            normalized_choice = "required" if tool_choice in (True, "required") else "any"
            return {
                "tools": tool_list,
                "tool_choice": normalized_choice,
                "output_schema": build_tool_response_schema(tool_list, allow_final=False),
                "tool_arguments_as_json_string": len(tool_list) > 1,
            }

        selected_tool_name = self._extract_named_tool_choice(tool_choice)
        if selected_tool_name is None:
            raise CodexStructuredOutputError(
                f"Unsupported Codex tool_choice value: {tool_choice!r}"
            )

        selected_tools = [
            tool
            for tool in tool_list
            if tool.get("function", {}).get("name") == selected_tool_name
        ]
        if not selected_tools:
            available = ", ".join(
                tool.get("function", {}).get("name", "<unknown>")
                for tool in tool_list
            )
            raise CodexStructuredOutputError(
                f"Requested tool_choice '{selected_tool_name}' is not in the bound tool set. "
                f"Available tools: {available}"
            )

        return {
            "tools": selected_tools,
            "tool_choice": selected_tool_name,
            "output_schema": build_tool_response_schema(selected_tools, allow_final=False),
            "tool_arguments_as_json_string": False,
        }

    def _extract_named_tool_choice(self, tool_choice: Any) -> str | None:
        if isinstance(tool_choice, str):
            return tool_choice

        if not isinstance(tool_choice, dict):
            return None

        function = tool_choice.get("function")
        if isinstance(function, dict):
            name = function.get("name")
            if isinstance(name, str) and name:
                return name

        name = tool_choice.get("name")
        if isinstance(name, str) and name:
            return name

        return None
