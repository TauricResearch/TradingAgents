import json
import os
from typing import Any, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI
from langchain_openai.chat_models.base import (
    _construct_responses_api_payload,
    _convert_message_to_dict,
)

from .base_client import BaseLLMClient, normalize_content
from .openai_auth import build_api_key_provider
from .validators import validate_model


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with normalized content output.

    The Responses API returns content as a list of typed blocks
    (reasoning, text, etc.). This normalizes to string for consistent
    downstream handling.
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

    def with_structured_output(self, schema, *, method=None, **kwargs):
        """Wrap with structured output, defaulting to function_calling for OpenAI.

        langchain-openai's Responses-API-parse path (the default for json_schema
        when use_responses_api=True) calls response.model_dump(...) on the OpenAI
        SDK's union-typed parsed response, which makes Pydantic emit ~20
        PydanticSerializationUnexpectedValue warnings per call. The function-calling
        path returns a plain tool-call shape that does not trigger that
        serialization, so it is the cleaner choice for our combination of
        use_responses_api=True + with_structured_output. Both paths use OpenAI's
        strict mode and produce the same typed Pydantic instance.
        """
        if method is None:
            method = "function_calling"
        return super().with_structured_output(schema, method=method, **kwargs)


def _is_codex_backend(base_url: Optional[str]) -> bool:
    return bool(base_url and "chatgpt.com/backend-api/codex" in str(base_url))


def _content_to_instruction_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    texts = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                texts.append(block.strip())
            elif isinstance(block, dict):
                block_type = block.get("type")
                if block_type in {"text", "input_text", "output_text"}:
                    text = str(block.get("text", "") or "").strip()
                    if text:
                        texts.append(text)
    return "\n".join(t for t in texts if t)


def _extract_codex_instructions(messages: Sequence[BaseMessage]) -> tuple[str, list[BaseMessage]]:
    instructions = []
    filtered_messages = []

    for message in messages:
        role = _convert_message_to_dict(message, api="responses").get("role")
        if role in {"system", "developer"}:
            text = _content_to_instruction_text(getattr(message, "content", None))
            if text:
                instructions.append(text)
        else:
            filtered_messages.append(message)

    merged_instructions = "\n\n".join(part for part in instructions if part).strip()
    if not merged_instructions:
        merged_instructions = "You are a helpful AI assistant."

    return merged_instructions, filtered_messages


def _normalize_codex_input_items(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_items = []
    for item in payload.get("input", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            normalized_items.append(item)
            continue

        role = item.get("role")
        content = item.get("content")
        if isinstance(content, str):
            if role == "assistant":
                item = {
                    **item,
                    "content": [{"type": "output_text", "text": content, "annotations": []}],
                }
            else:
                item = {
                    **item,
                    "content": [{"type": "input_text", "text": content}],
                }
        normalized_items.append(item)

    payload["input"] = normalized_items
    return payload


class CodexChatOpenAI(NormalizedChatOpenAI):
    """ChatOpenAI shim for the ChatGPT Codex backend used by Hermes OAuth.

    The backend at chatgpt.com/backend-api/codex is not a drop-in replacement for
    the normal OpenAI /v1 API. It requires:
    - instructions to be present as a top-level field
    - input to be list-shaped
    - store=False
    - stream=True

    LangChain's default non-streaming Responses API path does not satisfy those
    constraints, so we translate system/developer messages into `instructions`
    and internally execute the request via the streaming Responses API even for
    normal `.invoke()` calls. We then hand the final OpenAI `Response` object
    back to LangChain's existing result-construction helper.
    """

    def _build_codex_payload(
        self,
        messages: Sequence[BaseMessage],
        *,
        stop: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], Any]:
        payload = {**self._default_params, **kwargs}
        if stop is not None:
            payload["stop"] = stop

        original_schema_obj = kwargs.get("response_format")
        instructions, filtered_messages = _extract_codex_instructions(messages)
        payload = _construct_responses_api_payload(filtered_messages, payload)
        payload = _normalize_codex_input_items(payload)
        payload["instructions"] = instructions
        payload["store"] = False
        payload["stream"] = True
        return payload, original_schema_obj

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        self._ensure_sync_client_available()
        payload, _ = self._build_codex_payload(messages, stop=stop, **kwargs)

        stream = self.root_client.responses.create(**payload)
        final_response = None
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        with stream as response_stream:
            for event in response_stream:
                event_type = getattr(event, "type", "")
                if event_type == "response.output_text.delta":
                    delta = getattr(event, "delta", "") or ""
                    text_parts.append(delta)
                    if run_manager:
                        run_manager.on_llm_new_token(delta)
                elif event_type == "response.output_item.done":
                    item = getattr(event, "item", None)
                    if getattr(item, "type", None) == "function_call":
                        raw_args = getattr(item, "arguments", "") or "{}"
                        try:
                            parsed_args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            parsed_args = raw_args
                        tool_calls.append(
                            {
                                "name": getattr(item, "name", ""),
                                "args": parsed_args,
                                "id": getattr(item, "call_id", None) or getattr(item, "id", None),
                                "type": "tool_call",
                            }
                        )
                elif event_type == "response.completed":
                    final_response = event.response

        if final_response is None:
            raise RuntimeError("Codex streaming response completed without a final response payload")

        usage_obj = getattr(final_response, "usage", None)
        usage = usage_obj.model_dump() if hasattr(usage_obj, "model_dump") else (usage_obj or {})
        response_metadata = {
            "id": getattr(final_response, "id", None),
            "model": getattr(final_response, "model", self.model_name),
            "status": getattr(final_response, "status", None),
            "service_tier": getattr(final_response, "service_tier", None),
            "model_provider": "openai",
            "model_name": getattr(final_response, "model", self.model_name),
        }
        response_metadata = {k: v for k, v in response_metadata.items() if v is not None}

        usage_metadata = None
        if usage:
            usage_metadata = {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "input_token_details": {"cache_read": usage.get("input_tokens_details", {}).get("cached_tokens", 0)},
                "output_token_details": {"reasoning": usage.get("output_tokens_details", {}).get("reasoning_tokens", 0)},
            }

        message = AIMessage(
            content="".join(text_parts),
            tool_calls=tool_calls,
            response_metadata=response_metadata,
            usage_metadata=usage_metadata,
            id=response_metadata.get("id"),
        )

        generation = ChatGeneration(message=message)
        return ChatResult(
            generations=[generation],
            llm_output={
                "token_usage": usage,
                "model_provider": "openai",
                "model_name": response_metadata.get("model_name", self.model_name),
                **({"id": response_metadata["id"]} if response_metadata.get("id") else {}),
                **({"service_tier": response_metadata["service_tier"]} if response_metadata.get("service_tier") else {}),
            },
        )

# Kwargs forwarded from user config to ChatOpenAI
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort",
    "api_key", "callbacks", "http_client", "http_async_client",
    "default_headers", "api_key_provider", "api_key_command",
)

# Provider base URLs and API key env vars
_PROVIDER_CONFIG = {
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "qwen": ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "glm": ("https://api.z.ai/api/paas/v4/", "ZHIPU_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
}


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI, Ollama, OpenRouter, and xAI providers.

    For native OpenAI models, uses the Responses API (/v1/responses) which
    supports reasoning_effort with function tools across all model families
    (GPT-4.1, GPT-5). Third-party compatible providers (xAI, OpenRouter,
    Ollama) use standard Chat Completions.
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        # Provider-specific base URL and auth
        if self.provider in _PROVIDER_CONFIG:
            base_url, api_key_env = _PROVIDER_CONFIG[self.provider]
            llm_kwargs["base_url"] = base_url
            if api_key_env:
                api_key = os.environ.get(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
            else:
                llm_kwargs["api_key"] = "ollama"
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url

        # Forward user-provided kwargs
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        resolved_api_key = build_api_key_provider(
            api_key=llm_kwargs.get("api_key"),
            api_key_provider=llm_kwargs.pop("api_key_provider", None),
            api_key_command=llm_kwargs.pop("api_key_command", None),
        )
        if resolved_api_key is not None:
            llm_kwargs["api_key"] = resolved_api_key

        # Native OpenAI: use Responses API for consistent behavior across
        # all model families. Third-party providers use Chat Completions.
        llm_class = NormalizedChatOpenAI
        if self.provider == "openai":
            llm_kwargs["use_responses_api"] = True
            if _is_codex_backend(llm_kwargs.get("base_url")):
                llm_class = CodexChatOpenAI

        return llm_class(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for the provider."""
        return validate_model(self.provider, self.model)
