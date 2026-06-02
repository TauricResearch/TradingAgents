from typing import Any, Optional

from langchain_google_genai import ChatGoogleGenerativeAI

from .base_client import BaseLLMClient, invoke_with_cache_and_retry, normalize_content
from .cache import LLMResponseCache
from .retry import RetryPolicy
from .validators import validate_model


class NormalizedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """ChatGoogleGenerativeAI with normalized content output.

    Gemini 3 models return content as list of typed blocks.
    This normalizes to string for consistent downstream handling.
    Cache + retry are wired through ``invoke_with_cache_and_retry`` when
    the wrapping client attaches ``_llm_cache`` / ``_retry_policy`` to
    the instance. The base ``ChatGoogleGenerativeAI.invoke`` is
    captured at ``__init__`` as ``_base_invoke`` so the wrapper can
    call the real entry point without re-entering this override.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._base_invoke = ChatGoogleGenerativeAI.invoke.__get__(self, type(self))

    def invoke(self, input, config=None, **kwargs):
        cache = getattr(self, "_llm_cache", None)
        retry_policy = getattr(self, "_retry_policy", None)
        if cache is None and (retry_policy is None or retry_policy.max_retries == 0):
            return normalize_content(self._base_invoke(input, config, **kwargs))
        response = invoke_with_cache_and_retry(
            self._base_invoke, self, input, config, kwargs,
            cache=cache, retry_policy=retry_policy,
        )
        return normalize_content(response)


class GoogleClient(BaseLLMClient):
    """Client for Google Gemini models."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatGoogleGenerativeAI instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model, "max_retries": 0}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in ("timeout", "max_retries", "temperature", "callbacks", "http_client", "http_async_client"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # Unified api_key maps to provider-specific google_api_key
        google_api_key = self.kwargs.get("api_key") or self.kwargs.get("google_api_key")
        if google_api_key:
            llm_kwargs["google_api_key"] = google_api_key

        # Map thinking_level to appropriate API param based on model
        # Gemini 3 Pro: low, high
        # Gemini 3 Flash: minimal, low, medium, high
        # Gemini 2.5: thinking_budget (0=disable, -1=dynamic)
        thinking_level = self.kwargs.get("thinking_level")
        if thinking_level:
            model_lower = self.model.lower()
            if "gemini-3" in model_lower:
                # Gemini 3 Pro doesn't support "minimal", use "low" instead
                if "pro" in model_lower and thinking_level == "minimal":
                    thinking_level = "low"
                llm_kwargs["thinking_level"] = thinking_level
            else:
                # Gemini 2.5: map to thinking_budget
                llm_kwargs["thinking_budget"] = -1 if thinking_level == "high" else 0

        instance = NormalizedChatGoogleGenerativeAI(**llm_kwargs)

        # Attach cache + retry policy post-init (see OpenAIClient).
        cache = self.kwargs.get("llm_cache")
        if isinstance(cache, LLMResponseCache):
            instance._llm_cache = cache
        retry_policy = self.kwargs.get("retry_policy")
        if isinstance(retry_policy, RetryPolicy):
            instance._retry_policy = retry_policy

        return instance

    def validate_model(self) -> bool:
        """Validate model for Google."""
        return validate_model("google", self.model)
