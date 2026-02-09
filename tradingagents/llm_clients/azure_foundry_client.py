import os
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient
from .validators import validate_model


class AzureFoundryClient(BaseLLMClient):
    """Client for models hosted on Azure AI Foundry.

    Azure AI Foundry exposes an OpenAI-compatible chat completions endpoint,
    so we use ChatOpenAI with a custom base_url pointing to your Foundry
    deployment.

    Required environment variables (unless passed explicitly):
        AZURE_FOUNDRY_ENDPOINT: Your Azure Foundry inference endpoint URI
            e.g. https://<resource>.services.ai.azure.com/models
                 https://<endpoint>.<region>.models.ai.azure.com/v1
        AZURE_FOUNDRY_API_KEY: Your Azure Foundry API key
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return a ChatOpenAI instance configured for Azure Foundry."""
        # Resolve endpoint: explicit kwarg > base_url > env var
        endpoint = (
            self.kwargs.get("azure_foundry_endpoint")
            or self.base_url
            or os.environ.get("AZURE_FOUNDRY_ENDPOINT")
        )
        if not endpoint:
            raise ValueError(
                "Azure Foundry endpoint is required. Set the AZURE_FOUNDRY_ENDPOINT "
                "environment variable, pass 'backend_url' in the config, or provide "
                "'azure_foundry_endpoint' in kwargs."
            )

        # Resolve API key: explicit kwarg > env var
        api_key = (
            self.kwargs.get("api_key")
            or os.environ.get("AZURE_FOUNDRY_API_KEY")
        )
        if not api_key:
            raise ValueError(
                "Azure Foundry API key is required. Set the AZURE_FOUNDRY_API_KEY "
                "environment variable or pass 'api_key' in kwargs."
            )

        llm_kwargs = {
            "model": self.model,
            "base_url": endpoint,
            "api_key": api_key,
        }

        # Forward optional params
        for key in ("timeout", "max_retries", "temperature", "max_tokens", "callbacks"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return ChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Azure Foundry."""
        return validate_model("azure_foundry", self.model)
