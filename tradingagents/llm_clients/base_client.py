import warnings
from abc import ABC, abstractmethod
from typing import Any


class EmptyModelResponseError(ValueError):
    """A provider returned neither answer text nor an executable tool call."""


def normalize_content(response):
    """Normalize LLM response content to a plain string.

    Multiple providers (OpenAI Responses API, Google Gemini 3) return content
    as a list of typed blocks, e.g. [{'type': 'reasoning', ...}, {'type': 'text', 'text': '...'}].
    Terminal reports need plain text. Tool turns retain native blocks because
    providers need their reasoning/signatures when the conversation continues.
    """
    metadata = getattr(response, "response_metadata", {}) or {}
    reason = metadata.get("stop_reason") or metadata.get("finish_reason") or "unknown"
    content = getattr(response, "content", None)
    if isinstance(content, list) and getattr(response, "tool_calls", None):
        return response
    if isinstance(content, list):
        texts = [
            item.get("text", "") if (isinstance(item, dict)
                and item.get("type") in {"text", "output_text"}
                and isinstance(item.get("text"), str)
                and not item.get("thought"))
            else item if isinstance(item, str) else ""
            for item in content
        ]
        response.content = "\n".join(t for t in texts if t)
    if not isinstance(response.content, str):
        raise EmptyModelResponseError("Model returned unsupported answer content; expected text or text blocks")
    if not response.content.strip() and not getattr(response, "tool_calls", None):
        raise EmptyModelResponseError(
            f"Model returned an empty response without tool calls (stop reason: {reason}). "
            "Check the model/backend and output token budget before retrying."
        )
    return response


def require_report_text(response, agent_name: str) -> str:
    """Validate a terminal agent answer, including custom and batch clients.

    A tool call is valid during an analyst's tool loop, but a no-tool agent
    cannot execute it and must never count it as a completed report.
    """
    response = normalize_content(response)
    if getattr(response, "tool_calls", None) or not response.content.strip():
        raise EmptyModelResponseError(f"{agent_name}: expected report text, received a tool call without a completed report")
    return response.content


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, model: str, base_url: str | None = None, **kwargs):
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
        """Validate that the model is supported by this client."""
        pass
