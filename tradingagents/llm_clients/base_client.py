from abc import ABC, abstractmethod
from typing import Any, Callable, Optional
import warnings

from .cache import LLMResponseCache, make_cache_key
from .retry import RetryPolicy, invoke_with_retry


def normalize_content(response):
    """Normalize LLM response content to a plain string.

    Multiple providers (OpenAI Responses API, Google Gemini 3) return content
    as a list of typed blocks, e.g. [{'type': 'reasoning', ...}, {'type': 'text', 'text': '...'}].
    Downstream agents expect response.content to be a string. This extracts
    and joins the text blocks, discarding reasoning/metadata blocks.
    """
    content = response.content
    if isinstance(content, list):
        texts = [
            item.get("text", "") if isinstance(item, dict) and item.get("type") == "text"
            else item if isinstance(item, str) else ""
            for item in content
        ]
        response.content = "\n".join(t for t in texts if t)
    return response


def invoke_with_cache_and_retry(
    base_invoke: Callable[..., Any],
    chat: Any,
    input: Any,
    config: Any,
    kwargs: dict,
    *,
    cache: Optional[LLMResponseCache] = None,
    retry_policy: Optional[RetryPolicy] = None,
) -> Any:
    """Wrap a base chat ``invoke`` call with cache lookup and retry-with-backoff.

    ``base_invoke`` MUST be the langchain chat's actual API-calling
    ``invoke`` (e.g. ``ChatOpenAI.invoke``), not the wrapping
    ``NormalizedChatOpenAI.invoke`` override — otherwise the override
    re-enters itself and the call recurses until the interpreter
    aborts. Callers in the override pass
    ``lambda *a, **kw: super().invoke(*a, **kw)`` or, more directly,
    the bound method obtained via ``ChatOpenAI.invoke.__get__(self)``.

    Resolution order on a call:

    1. Compute the cache key from ``(model, messages, tools, tool_choice, ...)``.
    2. If a cache is configured and the key hits, return the cached
       ``AIMessage`` without making a network call.
    3. Otherwise call ``base_invoke(input, config, **kwargs)`` through
       ``invoke_with_retry`` so 429/5xx are absorbed.
    4. On success, write the response to the cache (best-effort) and
       return it.

    Both the cache and the policy are optional; passing neither yields
    a plain ``base_invoke`` call, matching the pre-feature behavior.
    """
    if cache is None and (retry_policy is None or retry_policy.max_retries == 0):
        return base_invoke(input, config, **kwargs)

    model_name = getattr(chat, "model_name", None) or getattr(chat, "model", "")

    # Build the cache key from the rendered request. We pass the same
    # kwargs that ``invoke`` will see so the key reflects the full
    # request shape, not just the message list.
    tools = kwargs.get("tools")
    tool_choice = kwargs.get("tool_choice")
    key = None
    if cache is not None and cache.enabled:
        key = make_cache_key(
            model_name,
            input,
            tools=tools,
            tool_choice=tool_choice,
            **{k: v for k, v in kwargs.items() if k not in ("tools", "tool_choice")},
        )
        cached = cache.get(key)
        if cached is not None:
            return cached

    if retry_policy is not None and retry_policy.max_retries > 0:
        response = invoke_with_retry(
            base_invoke, input, config, policy=retry_policy, **kwargs,
        )
    else:
        response = base_invoke(input, config, **kwargs)

    if cache is not None and cache.enabled and key is not None:
        cache.put(key, response)

    return response


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        self.model = model
        self.base_url = base_url
        self.kwargs = kwargs

    def get_provider_name(self) -> str:
        """Return the provider name used in warning messages."""
        provider = getattr(self, "provider", None)
        if provider:
            return str(provider)
        return self.__class__.__name__.removesuffix("Client").lower()

    def warn_if_unknown_model(self) -> None:
        """Warn when the model is outside the known list for the provider."""
        if self.validate_model():
            return

        warnings.warn(
            (
                f"Model '{self.model}' is not in the known model list for "
                f"provider '{self.get_provider_name()}'. Continuing anyway."
            ),
            RuntimeWarning,
            stacklevel=2,
        )

    @abstractmethod
    def get_llm(self) -> Any:
        """Return the configured LLM instance."""
        pass

    @abstractmethod
    def validate_model(self) -> bool:
        """Validate that this model is supported by this client."""
        pass
