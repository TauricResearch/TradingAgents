from typing import Any, Optional, List

from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

# Dummy value sanctioned by Google to skip thought_signature validation.
# See https://ai.google.dev/gemini-api/docs/thought-signatures#faqs
_SKIP_THOUGHT_SIG = b"skip_thought_signature_validator"


def _inject_thought_signatures(request: Any) -> Any:
    """Add dummy thought_signature to function-call parts in Gemini 3 requests.

    langchain-google-genai <=2.x does not preserve thought_signature fields
    returned by the API, causing 400 errors on the next turn.  Google's FAQ
    allows a well-known dummy value to bypass server-side validation.
    """
    for content in request.contents:
        if content.role != "model":
            continue
        first_fc = True
        for part in content.parts:
            if part.function_call.name:  # has a function call
                if first_fc:
                    part.thought_signature = _SKIP_THOUGHT_SIG
                    first_fc = False
    return request


class NormalizedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """ChatGoogleGenerativeAI with normalized content output.

    Gemini 3 models return content as list of typed blocks.
    This normalizes to string for consistent downstream handling.
    Also injects dummy thought signatures for Gemini 3 function calling.
    """

    def _prepare_request(
        self,
        messages: List[BaseMessage],
        **kwargs: Any,
    ) -> Any:
        request = super()._prepare_request(messages, **kwargs)
        if "gemini-3" in (self.model or "").lower():
            _inject_thought_signatures(request)
        return request

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))


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

        return NormalizedChatGoogleGenerativeAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Google."""
        return validate_model("google", self.model)
