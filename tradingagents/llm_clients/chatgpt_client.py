"""ChatGPT subscription Responses adapter.

Public LangChain chat model over the OpenAI SDK, plus a BaseLLMClient wrapper.
Requests stay on the documented public Responses endpoint: stateless, streamed,
and with local tools grouped under the ``tradingagents`` namespace. API-key
provider capabilities are left untouched.
"""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlparse

from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ChatMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.utils.function_calling import convert_to_openai_tool
from openai import OpenAI
from pydantic import ConfigDict, Field, SecretStr, model_validator

from tradingagents.llm_clients.base_client import BaseLLMClient

PUBLIC_RESPONSES_BASE_URL = "https://api.openai.com/v1"
TOOL_NAMESPACE = "tradingagents"
RESPONSES_OUTPUT_KEY = "responses_output"
_NAMESPACE_DESCRIPTION = "TradingAgents local function and custom tools."

# Temperature and output caps are omitted rather than applied. Conversation
# state is resent in full instead of previous_response_id.
_OMIT_BODY_KEYS = frozenset(
    {
        "temperature",
        "max_output_tokens",
        "max_tokens",
        "max_completion_tokens",
        "previous_response_id",
        "use_previous_response_id",
    }
)
_REJECT_BODY_KEYS = frozenset(
    {
        "background",
        "conversation",
        "max_tool_calls",
        "metadata",
        "moderation",
        "multi_agent",
        "prompt",
        "prompt_cache_key",
        "prompt_cache_retention",
        "response_format",
        "safety_identifier",
        "text",
        "top_logprobs",
        "top_p",
        "truncation",
        "user",
    }
)
_ENDPOINT_KEYS = frozenset(
    {
        "base_url",
        "openai_api_base",
        "api_base",
        "endpoint",
        "openai_base_url",
        "azure_endpoint",
        "url",
    }
)
_CREDENTIAL_KEYS = frozenset(
    {
        "api_key",
        "openai_api_key",
        "token",
        "access_token",
        "authorization",
        "default_headers",
        "extra_headers",
        "headers",
        "http_client",
        "http_async_client",
    }
)
_ALLOWED_HOSTED_TOOLS = frozenset({"web_search", "web_search_preview"})
_LANGCHAIN_NOISE = frozenset({"callbacks", "tags", "run_id", "configurable", "recursion_limit"})


class ChatGPTResponsesError(ValueError):
    """The Responses request or tool call cannot be sent or accepted."""


def _is_public_base_url(url: str | None) -> bool:
    """True only for the documented public API root, with no user, query, or port."""
    if url is None:
        return True
    if not isinstance(url, str):
        return False
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != "api.openai.com":
        return False
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port:
        return False
    return parsed.path.rstrip("/") == "/v1"


def _text_parts(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}]
    if not isinstance(content, list):
        text = "" if content is None else str(content)
        return [{"type": "input_text", "text": text}]
    parts: list[dict[str, Any]] = []
    for block in content:
        if isinstance(block, str):
            parts.append({"type": "input_text", "text": block})
            continue
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type in {"text", "output_text", "input_text"}:
            parts.append({"type": "input_text", "text": str(block.get("text") or "")})
        elif block_type == "image_url":
            image = block.get("image_url")
            url = image.get("url") if isinstance(image, dict) else image
            if isinstance(url, str) and url:
                parts.append({"type": "input_image", "image_url": url})
        elif block_type in {"input_image", "input_file"}:
            parts.append(dict(block))
        elif isinstance(block.get("text"), str):
            parts.append({"type": "input_text", "text": block["text"]})
    return parts or [{"type": "input_text", "text": ""}]


def _plain_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(
        part["text"]
        for part in _text_parts(content)
        if part.get("type") == "input_text" and part.get("text")
    )


def _message_item(role: str, content: Any) -> dict[str, Any]:
    if role == "system":
        role = "developer"
    return {"type": "message", "role": role, "content": _text_parts(content)}


def _require_object_schema(parameters: Any, name: str) -> dict[str, Any]:
    label = name or "<unnamed>"
    if not isinstance(parameters, dict):
        raise ChatGPTResponsesError(f"bad tool schema for {label}")
    schema_type = parameters.get("type")
    if schema_type not in {None, "object"}:
        raise ChatGPTResponsesError(f"bad tool schema for {label}")
    properties = parameters.get("properties")
    if properties is not None and not isinstance(properties, dict):
        raise ChatGPTResponsesError(f"bad tool schema for {label}")
    return parameters


def _function_spec(name: Any, description: Any, parameters: Any, strict: Any) -> dict[str, Any]:
    if not isinstance(name, str) or not name:
        raise ChatGPTResponsesError("bad tool schema for <unnamed>")
    spec: dict[str, Any] = {
        "type": "function",
        "name": name,
        "parameters": _require_object_schema(parameters, name),
    }
    if isinstance(description, str) and description:
        spec["description"] = description
    if isinstance(strict, bool):
        spec["strict"] = strict
    return spec


def _normalize_tool(tool: Any) -> dict[str, Any]:
    """Return a function, custom, or allowed hosted tool. Other hosted tools are rejected."""
    if isinstance(tool, dict):
        tool_type = tool.get("type")
        if tool_type == "custom" or (tool_type is None and "name" in tool and "format" in tool):
            name = tool.get("name")
            if not isinstance(name, str) or not name:
                raise ChatGPTResponsesError("bad tool schema for <unnamed>")
            spec: dict[str, Any] = {"type": "custom", "name": name}
            description = tool.get("description")
            if isinstance(description, str) and description:
                spec["description"] = description
            if isinstance(tool.get("format"), dict):
                spec["format"] = dict(tool["format"])
            return spec
        if tool_type == "function" and isinstance(tool.get("function"), dict):
            function = tool["function"]
            return _function_spec(
                function.get("name"),
                function.get("description"),
                function.get("parameters"),
                function.get("strict", tool.get("strict")),
            )
        if tool_type == "function" and "name" in tool and "function" not in tool:
            return _function_spec(
                tool.get("name"),
                tool.get("description"),
                tool.get("parameters"),
                tool.get("strict"),
            )
        if isinstance(tool_type, str) and tool_type in _ALLOWED_HOSTED_TOOLS:
            return dict(tool)
        if isinstance(tool_type, str):
            raise ChatGPTResponsesError(f"unsupported hosted tool {tool_type}")
    converted = convert_to_openai_tool(tool)
    function = converted.get("function", converted)
    return _function_spec(
        function.get("name"),
        function.get("description"),
        function.get("parameters"),
        function.get("strict"),
    )


def _wire_tools(tools: Iterable[Any]) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    functions: list[dict[str, Any]] = []
    customs: list[dict[str, Any]] = []
    hosted: list[dict[str, Any]] = []
    function_names: set[str] = set()
    custom_names: set[str] = set()
    for tool in tools:
        spec = _normalize_tool(tool)
        if spec["type"] == "function":
            functions.append(spec)
            function_names.add(spec["name"])
        elif spec["type"] == "custom":
            customs.append(spec)
            custom_names.add(spec["name"])
        else:
            hosted.append(spec)
    wired: list[dict[str, Any]] = []
    local = functions + customs
    if local:
        wired.append(
            {
                "type": "namespace",
                "name": TOOL_NAMESPACE,
                "description": _NAMESPACE_DESCRIPTION,
                "tools": local,
            }
        )
    wired.extend(hosted)
    return wired, function_names, custom_names


def _tool_choice_value(tool_choice: Any, *, structured: bool) -> Any:
    if structured or tool_choice in {"any", "required"}:
        return "required"
    if tool_choice is None:
        return None
    if tool_choice in {"auto", "none"}:
        return tool_choice
    if isinstance(tool_choice, str):
        return {"type": "function", "name": tool_choice}
    if isinstance(tool_choice, dict):
        choice_type = tool_choice.get("type")
        allowed = choice_type in _ALLOWED_HOSTED_TOOLS or choice_type in {"function", "custom"}
        if allowed:
            return dict(tool_choice)
        if choice_type:
            raise ChatGPTResponsesError(f"unsupported hosted tool {choice_type}")
    raise ChatGPTResponsesError("unsupported tool_choice")


def _output_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return copy.deepcopy(item)
    dump = getattr(item, "model_dump", None)
    if dump is None:
        raise ChatGPTResponsesError("response output item is not serializable")
    dumped = dump(exclude_none=True, mode="json", by_alias=True)
    if not isinstance(dumped, dict):
        raise ChatGPTResponsesError("response output item is not serializable")
    return dumped


def _parse_arguments(raw: Any, name: str) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        raise ChatGPTResponsesError(f"malformed function call arguments for {name}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ChatGPTResponsesError(f"malformed function call arguments for {name}") from exc
    if not isinstance(parsed, dict):
        raise ChatGPTResponsesError(f"function call arguments for {name} must be an object")
    return parsed


def _remember_call(item: dict[str, Any], kinds: dict[str, str], names: dict[str, str]) -> None:
    call_id = item.get("call_id")
    if not isinstance(call_id, str) or not call_id:
        return
    item_type = item.get("type")
    if item_type == "function_call":
        kinds[call_id] = "function"
        if isinstance(item.get("name"), str):
            names[call_id] = item["name"]
    elif item_type == "custom_tool_call":
        kinds[call_id] = "custom"
        if isinstance(item.get("name"), str):
            names[call_id] = item["name"]


def _with_namespace(item: dict[str, Any]) -> dict[str, Any]:
    cloned = copy.deepcopy(item)
    if cloned.get("type") in {"function_call", "custom_tool_call", "function_call_output"}:
        cloned["namespace"] = TOOL_NAMESPACE
    return cloned


def _assistant_items(
    message: AIMessage,
    kinds: dict[str, str],
    names: dict[str, str],
) -> list[dict[str, Any]]:
    stored = message.additional_kwargs.get(RESPONSES_OUTPUT_KEY)
    if stored is not None:
        if not isinstance(stored, list):
            raise ChatGPTResponsesError("stored responses output is malformed")
        # Lossless items already contain reasoning, text, and calls in order.
        # Do not rebuild that turn from the normalized text content.
        replayed: list[dict[str, Any]] = []
        for item in stored:
            if not isinstance(item, dict):
                raise ChatGPTResponsesError("stored responses output item is malformed")
            cloned = _with_namespace(item)
            replayed.append(cloned)
            _remember_call(cloned, kinds, names)
        return replayed
    items: list[dict[str, Any]] = []
    text = _plain_text(message.content)
    if text or not message.tool_calls:
        items.append(
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        )
    for tool_call in message.tool_calls:
        call_id = tool_call.get("id")
        name = tool_call.get("name")
        if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
            raise ChatGPTResponsesError("malformed function call")
        item = {
            "type": "function_call",
            "name": name,
            "arguments": json.dumps(tool_call.get("args") or {}),
            "call_id": call_id,
            "namespace": TOOL_NAMESPACE,
        }
        items.append(item)
        _remember_call(item, kinds, names)
    return items


def _tool_result(
    message: ToolMessage,
    kinds: dict[str, str],
    names: dict[str, str],
) -> dict[str, Any]:
    call_id = message.tool_call_id
    if not isinstance(call_id, str) or not call_id:
        raise ChatGPTResponsesError("malformed function call output")
    output = message.content if isinstance(message.content, str) else json.dumps(message.content)
    if kinds.get(call_id) == "custom":
        return {"type": "custom_tool_call_output", "call_id": call_id, "output": output}
    result: dict[str, Any] = {
        "type": "function_call_output",
        "call_id": call_id,
        "output": output,
        "namespace": TOOL_NAMESPACE,
    }
    name = message.name or names.get(call_id)
    if isinstance(name, str) and name:
        result["name"] = name
    return result


def _history_items(messages: Iterable[BaseMessage]) -> list[dict[str, Any]]:
    """Convert the full LangChain turn, including prior tool calls, to Responses input."""
    items: list[dict[str, Any]] = []
    kinds: dict[str, str] = {}
    names: dict[str, str] = {}
    for message in messages:
        if isinstance(message, AIMessage):
            items.extend(_assistant_items(message, kinds, names))
        elif isinstance(message, ToolMessage):
            items.append(_tool_result(message, kinds, names))
        elif isinstance(message, SystemMessage):
            items.append(_message_item("developer", message.content))
        elif isinstance(message, HumanMessage):
            items.append(_message_item("user", message.content))
        elif isinstance(message, ChatMessage):
            role = "developer" if message.role == "system" else message.role
            if role not in {"developer", "user", "assistant"}:
                raise ChatGPTResponsesError(f"unsupported message role {role}")
            items.append(_message_item(role, message.content))
        else:
            raise ChatGPTResponsesError(f"unsupported message type {type(message).__name__}")
    return items


def _calls_from_items(
    items: list[dict[str, Any]],
    function_names: set[str],
    custom_names: set[str],
) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    for item in items:
        item_type = item.get("type")
        if item_type not in {"function_call", "custom_tool_call"}:
            continue
        name = item.get("name")
        namespace = item.get("namespace")
        call_id = item.get("call_id")
        if namespace != TOOL_NAMESPACE:
            raise ChatGPTResponsesError(
                f"function call namespace {namespace!r} is not {TOOL_NAMESPACE}"
            )
        if not isinstance(call_id, str) or not call_id:
            raise ChatGPTResponsesError("function call is missing call_id")
        if item_type == "function_call":
            if not isinstance(name, str) or name not in function_names:
                raise ChatGPTResponsesError(f"unknown function call {name!r}")
            args = _parse_arguments(item.get("arguments"), name)
            tool_calls.append({"name": name, "args": args, "id": call_id, "type": "tool_call"})
            continue
        if not isinstance(name, str) or name not in custom_names:
            raise ChatGPTResponsesError(f"unknown function call {name!r}")
        custom_input = item.get("input")
        if not isinstance(custom_input, str):
            raise ChatGPTResponsesError(f"malformed function call arguments for {name}")
        tool_calls.append(
            {"name": name, "args": {"__arg1": custom_input}, "id": call_id, "type": "tool_call"}
        )
    return tool_calls


def _message_text(items: list[dict[str, Any]]) -> str:
    texts: list[str] = []
    for item in items:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                text = part.get("text")
                if isinstance(text, str) and text:
                    texts.append(text)
    return "\n".join(texts)


def _completed_response(stream: Iterable[Any]) -> Any:
    """Accept one completed Responses stream. Failure events are not success."""
    completed = None
    for event in stream:
        event_type = getattr(event, "type", None)
        if event_type == "response.completed":
            completed = event.response
        elif event_type in {"response.failed", "response.incomplete", "error"}:
            raise ChatGPTResponsesError(f"response ended with {event_type}")
    if completed is None:
        raise ChatGPTResponsesError("stream ended without response.completed")
    return completed


class ChatGPTResponses(BaseChatModel):
    """Responses-only chat model for a ChatGPT plan access token.

    ``store`` is always false, ``stream`` is always true, and
    ``use_previous_response_id`` stays false. System messages are sent as
    developer messages. The complete prior turn is replayed from ordered
    Responses output items stored on the assistant message.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

    model_name: str = Field(alias="model")
    api_key: SecretStr | None = Field(default=None, repr=False)
    base_url: str = PUBLIC_RESPONSES_BASE_URL
    use_previous_response_id: bool = False
    timeout: float | None = None
    http_client: Any = Field(default=None, exclude=True, repr=False)
    http_async_client: Any = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def _pin_public_endpoint(self) -> ChatGPTResponses:
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model is required")
        if not _is_public_base_url(self.base_url):
            raise ValueError("ChatGPT Responses rejects a custom endpoint")
        if self.use_previous_response_id:
            raise ValueError("ChatGPT Responses keeps use_previous_response_id false")
        self.base_url = PUBLIC_RESPONSES_BASE_URL
        return self

    @property
    def _llm_type(self) -> str:
        return "chatgpt-responses"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model": self.model_name}

    def bind_tools(
        self,
        tools: Iterable[Any],
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        formatted = [_normalize_tool(tool) for tool in tools]
        return super().bind(tools=formatted, tool_choice=tool_choice, **kwargs)

    def _access_token(self) -> str:
        if self.api_key is not None:
            value = self.api_key.get_secret_value()
            if value:
                return value
        value = os.environ.get("ACCESS_TOKEN")
        if value:
            return value
        raise ChatGPTResponsesError("ChatGPT access token is not set")

    def _reject_transport_overrides(self, params: Mapping[str, Any]) -> None:
        if _ENDPOINT_KEYS.intersection(params):
            raise ChatGPTResponsesError("ChatGPT Responses rejects a custom endpoint")
        if _CREDENTIAL_KEYS.intersection(params):
            raise ChatGPTResponsesError("ChatGPT Responses rejects token and API-key overrides")

    def _consume_extra_body(self, extra: Any) -> None:
        if extra is None:
            return
        if not isinstance(extra, Mapping):
            raise ChatGPTResponsesError("malformed extra_body")
        keys = set(extra)
        if keys.intersection(_ENDPOINT_KEYS) or keys.intersection(_CREDENTIAL_KEYS):
            raise ChatGPTResponsesError("malformed extra_body")
        remaining = keys - _OMIT_BODY_KEYS
        if remaining:
            raise ChatGPTResponsesError("malformed extra_body")

    def _prepare_body(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None,
        params: dict[str, Any],
    ) -> tuple[dict[str, Any], set[str], set[str], float | None]:
        # Overrides are rejected before the SDK client, which is what attaches the bearer.
        self._reject_transport_overrides(params)
        self._consume_extra_body(params.pop("extra_body", None))
        if params.get("use_previous_response_id"):
            raise ChatGPTResponsesError("ChatGPT Responses keeps use_previous_response_id false")
        if stop:
            raise ChatGPTResponsesError("unsupported setting stop")
        for key in list(params):
            if key in _OMIT_BODY_KEYS:
                params.pop(key)
        if params.get("store") is True:
            raise ChatGPTResponsesError("ChatGPT Responses requires store false")
        if params.get("stream") is False:
            raise ChatGPTResponsesError("ChatGPT Responses requires streaming")
        for key in ("store", "stream", "max_retries"):
            params.pop(key, None)
        tools = params.pop("tools", None)
        tool_choice = params.pop("tool_choice", None)
        structured = params.pop("ls_structured_output_format", None) is not None
        timeout = params.pop("timeout", None)
        for key in list(params):
            if key.startswith("ls_") or key in _LANGCHAIN_NOISE:
                params.pop(key)
        unsupported = _REJECT_BODY_KEYS.intersection(params)
        if unsupported:
            raise ChatGPTResponsesError(f"unsupported setting {sorted(unsupported)[0]}")
        if params:
            raise ChatGPTResponsesError(f"unsupported setting {sorted(params)[0]}")

        wired: list[dict[str, Any]] = []
        function_names: set[str] = set()
        custom_names: set[str] = set()
        if tools:
            wired, function_names, custom_names = _wire_tools(tools)
        choice = _tool_choice_value(tool_choice, structured=structured)
        body: dict[str, Any] = {
            "model": self.model_name,
            "input": _history_items(messages),
            "store": False,
            "stream": True,
            "include": ["reasoning.encrypted_content"],
        }
        if wired:
            body["tools"] = wired
        if choice is not None and wired:
            body["tool_choice"] = choice
        # LangChain pops ls_structured_output_format before _generate. A schema
        # bind is tool_choice any/required plus one local tool; that must force
        # a single Responses tool call.
        one_local_tool = len(function_names) + len(custom_names) == 1
        if structured or (choice == "required" and one_local_tool):
            body["tool_choice"] = "required"
            body["parallel_tool_calls"] = False
        if _OMIT_BODY_KEYS.intersection(body):
            raise ChatGPTResponsesError("omitted Responses fields were still serialized")
        return body, function_names, custom_names, timeout

    def _client(self) -> OpenAI:
        kwargs: dict[str, Any] = {
            "api_key": self._access_token(),
            "base_url": PUBLIC_RESPONSES_BASE_URL,
            "max_retries": 0,
        }
        if self.http_client is not None:
            kwargs["http_client"] = self.http_client
        if self.timeout is not None:
            kwargs["timeout"] = self.timeout
        return OpenAI(**kwargs)

    def _message_from_response(
        self,
        response: Any,
        function_names: set[str],
        custom_names: set[str],
    ) -> AIMessage:
        raw_output = getattr(response, "output", []) or []
        items = [_output_item(item) for item in raw_output]
        tool_calls = _calls_from_items(items, function_names, custom_names)
        fields: dict[str, Any] = {
            "content": _message_text(items),
            "additional_kwargs": {RESPONSES_OUTPUT_KEY: items},
            "response_metadata": {"model_provider": "chatgpt", "model": self.model_name},
        }
        if tool_calls:
            fields["tool_calls"] = tool_calls
        response_id = getattr(response, "id", None)
        if isinstance(response_id, str):
            fields["id"] = response_id
        return AIMessage(**fields)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del run_manager
        body, function_names, custom_names, timeout = self._prepare_body(
            messages, stop, dict(kwargs)
        )
        request = dict(body)
        if timeout is not None:
            request["timeout"] = timeout
        client = self._client()
        with client.responses.create(**request) as stream:
            response = _completed_response(stream)
        message = self._message_from_response(response, function_names, custom_names)
        return ChatResult(generations=[ChatGeneration(message=message)])


class ChatGPTClient(BaseLLMClient):
    """Wrapper that returns the ChatGPT Responses chat model.

    Custom endpoints are rejected here, before a token can be attached. Temperature
    and output-cap kwargs are not forwarded, so they cannot be presented as if
    this route applied them. Model-capability tables for API-key providers are
    not consulted or updated.
    """

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        provider: str = "chatgpt",
        **kwargs: Any,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider
        if not _is_public_base_url(base_url):
            raise ValueError("ChatGPT Responses rejects a custom endpoint")
        if _ENDPOINT_KEYS.intersection(kwargs):
            raise ValueError("ChatGPT Responses rejects a custom endpoint")

    def get_llm(self) -> ChatGPTResponses:
        self.warn_if_unknown_model()
        forwarded: dict[str, Any] = {}
        for key in ("api_key", "timeout", "callbacks", "http_client", "http_async_client"):
            if key in self.kwargs and self.kwargs[key] is not None:
                forwarded[key] = self.kwargs[key]
        return ChatGPTResponses(model=self.model, **forwarded)

    def validate_model(self) -> bool:
        return isinstance(self.model, str) and bool(self.model.strip())
