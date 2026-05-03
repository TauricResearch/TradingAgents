import os
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


_RETIRED_DEEPSEEK_MODELS = {"deepseek-chat", "deepseek-reasoner"}


def reject_retired_deepseek_model(model: str) -> None:
    """Reject DeepSeek model IDs that should no longer be silently aliased."""
    if model in _RETIRED_DEEPSEEK_MODELS:
        raise ValueError(
            f"DeepSeek model '{model}' is retired for TradingAgents. "
            "Use 'deepseek-v4-flash' or 'deepseek-v4-pro' instead."
        )


def _copy_message_without_reasoning_content(message):
    if isinstance(message, dict):
        cleaned = dict(message)
        cleaned.pop("reasoning_content", None)
        return cleaned

    copied = (
        message.model_copy(deep=True)
        if hasattr(message, "model_copy")
        else message.copy(deep=True)
    )

    additional_kwargs = getattr(copied, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        additional_kwargs.pop("reasoning_content", None)

    if hasattr(copied, "reasoning_content"):
        copied.reasoning_content = None

    return copied


def strip_deepseek_reasoning_content(input):
    """Remove stale DeepSeek thinking content from outbound message history."""
    if isinstance(input, list):
        return [_copy_message_without_reasoning_content(message) for message in input]
    if isinstance(input, tuple):
        return tuple(_copy_message_without_reasoning_content(message) for message in input)
    return input


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


class DeepSeekChatOpenAI(NormalizedChatOpenAI):
    """DeepSeek-compatible chat model with stale thinking metadata removed."""

    def invoke(self, input, config=None, **kwargs):
        input = strip_deepseek_reasoning_content(input)
        return super().invoke(input, config, **kwargs)

# Kwargs forwarded from user config to ChatOpenAI
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort",
    "api_key", "callbacks", "http_client", "http_async_client",
    "extra_body",
)

# Provider base URLs and API key env vars
_PROVIDER_CONFIG = {
    "xai": ("https://api.x.ai/v1", ("XAI_API_KEY",)),
    "deepseek": ("https://api.deepseek.com", ("DEEPSEEK_API_KEY",)),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", ("DASHSCOPE_API_KEY",)),
    "glm": ("https://api.z.ai/api/paas/v4/", ("ZAI_API_KEY", "ZHIPU_API_KEY")),
    "openrouter": ("https://openrouter.ai/api/v1", ("OPENROUTER_API_KEY",)),
    "ollama": ("http://localhost:11434/v1", None),
}

_BASE_URL_ENV = {
    "xai": ("XAI_BASE_URL",),
    "deepseek": ("DEEPSEEK_BASE_URL",),
    "qwen": ("DASHSCOPE_BASE_URL", "QWEN_BASE_URL"),
    "glm": ("ZAI_BASE_URL", "GLM_BASE_URL"),
    "openrouter": ("OPENROUTER_BASE_URL",),
    "ollama": ("OLLAMA_BASE_URL",),
}


def _first_env_value(names: tuple[str, ...]) -> str | None:
    return next((os.environ.get(name) for name in names if os.environ.get(name)), None)


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
        if self.provider == "deepseek":
            reject_retired_deepseek_model(self.model)
        self.warn_if_unknown_model()
        model = self.model
        llm_kwargs = {"model": model}

        # Provider-specific base URL and auth
        if self.provider in _PROVIDER_CONFIG:
            default_base_url, api_key_envs = _PROVIDER_CONFIG[self.provider]
            base_url_envs = _BASE_URL_ENV.get(self.provider, ())
            llm_kwargs["base_url"] = self.base_url or _first_env_value(base_url_envs) or default_base_url
            if api_key_envs:
                api_key = _first_env_value(api_key_envs)
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

        # DeepSeek V4 enables thinking mode by default on some models.
        # Thinking + tool calls
        # requires preserving provider-specific reasoning_content across every
        # subsequent tool turn, which LangChain does not reliably round-trip.
        # Use non-thinking mode for agent tool calls unless explicitly
        # overridden by the caller.
        if self.provider == "deepseek" and "extra_body" not in llm_kwargs:
            llm_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

        # Native OpenAI: use Responses API for consistent behavior across
        # all model families. Third-party providers use Chat Completions.
        if self.provider == "openai":
            llm_kwargs["use_responses_api"] = True

        chat_model_cls = (
            DeepSeekChatOpenAI
            if self.provider == "deepseek"
            else NormalizedChatOpenAI
        )
        return chat_model_cls(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for the provider."""
        return validate_model(self.provider, self.model)
