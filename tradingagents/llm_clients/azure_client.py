import os
from typing import Any, Optional

from langchain_openai import AzureChatOpenAI

from .base_client import BaseLLMClient, invoke_with_cache_and_retry, normalize_content
from .cache import LLMResponseCache
from .retry import RetryPolicy
from .validators import validate_model

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "reasoning_effort", "temperature",
    "callbacks", "http_client", "http_async_client",
)


class NormalizedAzureChatOpenAI(AzureChatOpenAI):
    """AzureChatOpenAI with normalized content output.

    Cache + retry are wired through ``invoke_with_cache_and_retry`` when
    the wrapping client attaches ``_llm_cache`` / ``_retry_policy`` to
    the instance. The base ``AzureChatOpenAI.invoke`` is captured at
    ``__init__`` as ``_base_invoke`` so the wrapper can call the real
    entry point without re-entering this override.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._base_invoke = AzureChatOpenAI.invoke.__get__(self, type(self))

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


class AzureOpenAIClient(BaseLLMClient):
    """Client for Azure OpenAI deployments.

    Requires environment variables:
        AZURE_OPENAI_API_KEY: API key
        AZURE_OPENAI_ENDPOINT: Endpoint URL (e.g. https://<resource>.openai.azure.com/)
        AZURE_OPENAI_DEPLOYMENT_NAME: Deployment name
        OPENAI_API_VERSION: API version (e.g. 2025-03-01-preview)
    """

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured AzureChatOpenAI instance."""
        self.warn_if_unknown_model()

        llm_kwargs = {
            "model": self.model,
            "azure_deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", self.model),
            "max_retries": 0,
        }

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        instance = NormalizedAzureChatOpenAI(**llm_kwargs)

        # Attach cache + retry policy post-init (see OpenAIClient).
        cache = self.kwargs.get("llm_cache")
        if isinstance(cache, LLMResponseCache):
            instance._llm_cache = cache
        retry_policy = self.kwargs.get("retry_policy")
        if isinstance(retry_policy, RetryPolicy):
            instance._retry_policy = retry_policy

        return instance

    def validate_model(self) -> bool:
        """Azure accepts any deployed model name."""
        return True
