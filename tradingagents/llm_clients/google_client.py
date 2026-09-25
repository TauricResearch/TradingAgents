from typing import Any, Optional

from langchain_core.runnables import Runnable
from langchain_google_genai import ChatGoogleGenerativeAI

from .base_client import BaseLLMClient, normalize_content
from .google_key_rotator import GoogleApiKeyRotator
from .validators import validate_model


class NormalizedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """ChatGoogleGenerativeAI with normalized content output.

    Gemini 3 models return content as list of typed blocks.
    This normalizes to string for consistent downstream handling.
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc)
    return "RESOURCE_EXHAUSTED" in text or "429" in text or "Quota exceeded" in text


class RotatingChatGoogleGenerativeAI(Runnable):
    """Gemini chat wrapper that rotates API keys for every request."""

    def __init__(self, llm_kwargs: dict[str, Any], api_keys: list[str], state_path: str, role: str = "default"):
        self.llm_kwargs = dict(llm_kwargs)
        self.rotator = GoogleApiKeyRotator(api_keys, state_path)
        self.role = role

    def _next_llm(self) -> NormalizedChatGoogleGenerativeAI:
        kwargs = dict(self.llm_kwargs)
        kwargs["google_api_key"] = self.rotator.next_key(role=self.role)
        return NormalizedChatGoogleGenerativeAI(**kwargs)

    def _with_key_failover(self, operation):
        last_exc = None
        for _ in range(max(1, len(self.rotator.api_keys))):
            try:
                return operation(self._next_llm())
            except Exception as exc:
                if not _is_quota_error(exc):
                    raise
                last_exc = exc
        raise last_exc

    def invoke(self, input, config=None, **kwargs):
        return self._with_key_failover(lambda llm: llm.invoke(input, config=config, **kwargs))

    def bind_tools(self, tools, **kwargs):
        return RotatingBoundGoogleGenerativeAI(self, tools, kwargs)

    def with_structured_output(self, schema, **kwargs):
        return RotatingStructuredGoogleGenerativeAI(self, schema, kwargs)


class RotatingBoundGoogleGenerativeAI(Runnable):
    """Tool-bound rotating Gemini wrapper."""

    def __init__(self, parent: RotatingChatGoogleGenerativeAI, tools, bind_kwargs: dict[str, Any]):
        self.parent = parent
        self.tools = tools
        self.bind_kwargs = dict(bind_kwargs)

    def invoke(self, input, config=None, **kwargs):
        def _invoke(llm):
            bound_llm = llm.bind_tools(self.tools, **self.bind_kwargs)
            return normalize_content(bound_llm.invoke(input, config=config, **kwargs))

        return self.parent._with_key_failover(_invoke)


class RotatingStructuredGoogleGenerativeAI(Runnable):
    """Structured-output rotating Gemini wrapper."""

    def __init__(self, parent: RotatingChatGoogleGenerativeAI, schema, structured_kwargs: dict[str, Any]):
        self.parent = parent
        self.schema = schema
        self.structured_kwargs = dict(structured_kwargs)

    def invoke(self, input, config=None, **kwargs):
        def _invoke(llm):
            structured_llm = llm.with_structured_output(
                self.schema, **self.structured_kwargs
            )
            return structured_llm.invoke(input, config=config, **kwargs)

        return self.parent._with_key_failover(_invoke)


class GoogleClient(BaseLLMClient):
    """Client for Google Gemini models."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatGoogleGenerativeAI instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in ("timeout", "max_retries", "callbacks", "http_client", "http_async_client"):
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

        api_keys = self.kwargs.get("api_keys")
        rotation_state_path = self.kwargs.get("rotation_state_path")
        if api_keys and rotation_state_path:
            llm_kwargs.pop("google_api_key", None)
            llm_kwargs.setdefault("max_retries", 0)
            return RotatingChatGoogleGenerativeAI(
                llm_kwargs=llm_kwargs,
                api_keys=list(api_keys),
                state_path=rotation_state_path,
                role=self.kwargs.get("role", "default"),
            )

        return NormalizedChatGoogleGenerativeAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Google."""
        return validate_model("google", self.model)
