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
        llm_kwargs = {
            "azure_deployment": self.model,
            "model": self.model,
        }

        # Prefer explicit config sources and let AzureChatOpenAI resolve env fallbacks.
        azure_endpoint = self.kwargs.get("azure_endpoint") or self.base_url
        if azure_endpoint:
            llm_kwargs["azure_endpoint"] = azure_endpoint

        for key in (
            "api_version",
            "api_key",
            "timeout",
            "max_retries",
            "reasoning_effort",
            "callbacks",
        ):
            if key in self.kwargs and self.kwargs[key] is not None:
                llm_kwargs[key] = self.kwargs[key]

        return AzureChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Azure OpenAI."""
        return validate_model("azure", self.model)
