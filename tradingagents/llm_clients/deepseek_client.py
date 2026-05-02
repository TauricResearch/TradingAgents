"""DeepSeek LLM client using langchain_deepseek's ChatDeepSeek.

Handles DeepSeek's reasoning_content requirement: when thinking mode is used,
the reasoning_content from the response must be preserved and passed back in
subsequent API requests. langchain_openai's ChatOpenAI does not support this.
"""

from __future__ import annotations

from typing import Any, Optional

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_deepseek import ChatDeepSeek

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

# Kwargs forwarded from user config to ChatDeepSeek
_PASSTHROUGH_KWARGS = (
    "timeout",
    "max_retries",
    "api_key",
    "callbacks",
    "http_client",
    "http_async_client",
)


class NormalizedChatDeepSeek(ChatDeepSeek):
    """ChatDeepSeek with normalized content and reasoning_content preservation.

    DeepSeek's API requires reasoning_content to be preserved across turns
    when using thinking/reasoning models. This class handles it in both
    directions: capturing reasoning_content from responses and injecting it
    back into request payloads.
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

    async def ainvoke(self, input, config=None, **kwargs):
        return normalize_content(await super().ainvoke(input, config, **kwargs))

    def with_structured_output(self, schema, *, method=None, **kwargs):
        if method is None:
            method = "function_calling"
        return super().with_structured_output(schema, method=method, **kwargs)

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        """Include reasoning_content from additional_kwargs in the request.

        DeepSeek's API requires that reasoning_content be passed back in
        subsequent requests when thinking mode is used. ChatDeepSeek stores
        it in additional_kwargs but doesn't include it in request payloads
        by default.
        """
        messages: list[BaseMessage]
        if isinstance(input_, list):
            messages = input_
        elif isinstance(input_, BaseMessage):
            messages = [input_]
        elif hasattr(input_, "to_messages"):
            messages = input_.to_messages()
        else:
            messages = self._convert_input(input_).to_messages()

        reasoning_values: list[Optional[str]] = [
            msg.additional_kwargs.get("reasoning_content")
            if isinstance(msg, AIMessage)
            else None
            for msg in messages
        ]

        payload = super()._get_request_payload(input_, stop=stop, **kwargs)

        # Apply reasoning_content to corresponding assistant message dicts.
        # super() processed messages 1:1, so index positions are preserved.
        if reasoning_values:
            for i, msg_dict in enumerate(payload["messages"]):
                if i < len(reasoning_values) and reasoning_values[i]:
                    msg_dict["reasoning_content"] = reasoning_values[i]

        return payload


class DeepSeekClient(BaseLLMClient):
    """Client for DeepSeek provider using ChatDeepSeek.

    Uses langchain_deepseek's ChatDeepSeek which properly handles
    reasoning_content and other DeepSeek-specific API requirements.
    """

    # ChatDeepSeek default includes /v1 suffix, but CLI passes base_url without it.
    # Only override api_base for non-default URLs.
    _DEFAULT_BASE = "https://api.deepseek.com"

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        llm_kwargs: dict[str, Any] = {"model": self.model}

        # Only set api_base if the user provided a custom (non-default) URL.
        # ChatDeepSeek handles its own default (https://api.deepseek.com/v1).
        if self.base_url and self.base_url.rstrip("/") != self._DEFAULT_BASE.rstrip("/"):
            llm_kwargs["api_base"] = self.base_url

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return NormalizedChatDeepSeek(**llm_kwargs)

    def validate_model(self) -> bool:
        return validate_model("deepseek", self.model)
