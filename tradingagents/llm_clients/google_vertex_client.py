import os
from typing import Any

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

_GOOGLE_VERTEX_CLASS = None


def _vertex_class():
    """Lazily import Vertex AI support and return a normalized ChatVertexAI."""
    global _GOOGLE_VERTEX_CLASS
    if _GOOGLE_VERTEX_CLASS is not None:
        return _GOOGLE_VERTEX_CLASS

    try:
        from langchain_google_vertexai import ChatVertexAI
    except ImportError as exc:
        raise ImportError(
            "Google Vertex AI support requires the optional "
            "'langchain-google-vertexai' dependency. "
            'Install it with: pip install "tradingagents[vertex]"'
        ) from exc

    class NormalizedChatVertexAI(ChatVertexAI):
        """ChatVertexAI with normalized content output."""

        def invoke(self, input, config=None, **kwargs):
            return normalize_content(super().invoke(input, config, **kwargs))

    _GOOGLE_VERTEX_CLASS = NormalizedChatVertexAI
    return _GOOGLE_VERTEX_CLASS


def _first_present(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None


class GoogleVertexClient(BaseLLMClient):
    """Client for Gemini models hosted on Google Vertex AI.

    Authentication uses Google Application Default Credentials, including
    ``GOOGLE_APPLICATION_CREDENTIALS``, gcloud ADC, or an attached service
    account. ``project`` and ``location`` may be passed directly or resolved
    from ``GOOGLE_CLOUD_PROJECT`` / ``GOOGLE_CLOUD_LOCATION``.
    """

    def get_llm(self) -> Any:
        """Return configured ChatVertexAI instance."""
        self.warn_if_unknown_model()
        chat_cls = _vertex_class()

        llm_kwargs = {"model": self.model}

        project = _first_present(
            self.kwargs.get("project"),
            self.kwargs.get("vertex_project"),
            os.environ.get("GOOGLE_CLOUD_PROJECT"),
            os.environ.get("VERTEXAI_PROJECT"),
        )
        if project:
            llm_kwargs["project"] = project

        location = _first_present(
            self.kwargs.get("location"),
            self.kwargs.get("vertex_location"),
            os.environ.get("GOOGLE_CLOUD_LOCATION"),
            os.environ.get("VERTEXAI_LOCATION"),
        )
        if location:
            llm_kwargs["location"] = location

        for key in (
            "credentials",
            "timeout",
            "max_retries",
            "temperature",
            "callbacks",
            "http_client",
            "http_async_client",
        ):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return chat_cls(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Google Vertex AI."""
        return validate_model("google_vertex", self.model)
