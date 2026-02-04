import os
from typing import Any, Optional

from langchain_openai import AzureChatOpenAI

from .base_client import BaseLLMClient
from .validators import validate_model


class AzureOpenAIClient(BaseLLMClient):
    """Client for Azure OpenAI models via AzureChatOpenAI."""

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured AzureChatOpenAI instance."""
        azure_endpoint = (
            self.kwargs.get("azure_endpoint")
            or self.base_url
            or os.environ.get("AZURE_OPENAI_ENDPOINT")
        )
        api_version = self.kwargs.get("api_version") or os.environ.get(
            "AZURE_OPENAI_API_VERSION",
            "2024-10-21",
        )
        api_key = self.kwargs.get("api_key") or os.environ.get("AZURE_OPENAI_API_KEY")

        llm_kwargs = {
            "azure_deployment": self.model,
            "model": self.model,
            "api_version": api_version,
        }

        if azure_endpoint:
            llm_kwargs["azure_endpoint"] = azure_endpoint
        if api_key:
            llm_kwargs["api_key"] = api_key

        for key in ("timeout", "max_retries", "reasoning_effort", "callbacks"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return AzureChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Azure OpenAI."""
        return validate_model("azure", self.model)
