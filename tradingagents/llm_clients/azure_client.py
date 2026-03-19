"""Azure OpenAI client implementation."""

import os
from typing import Any, Optional

from langchain_openai import AzureChatOpenAI

from .base_client import BaseLLMClient


class AzureClient(BaseLLMClient):
    """Client for Azure OpenAI provider.

    Required environment variables:
        AZURE_OPENAI_API_KEY: Your Azure OpenAI API key
        AZURE_OPENAI_ENDPOINT: Your Azure endpoint (e.g., https://your-resource.openai.azure.com/)
        OPENAI_API_VERSION: API version (e.g., 2024-02-15-preview)

    Optional:
        AZURE_DEPLOYMENT_NAME: Your deployment name (can also be passed as model parameter)
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        # In Azure, model is the deployment name
        self.deployment_name = model

    def get_llm(self) -> Any:
        """Return configured AzureChatOpenAI instance."""
        llm_kwargs = {
            "azure_deployment": self.deployment_name,
        }

        # Pass through Azure-specific kwargs
        for key in ("timeout", "max_retries", "callbacks", "api_version",
                    "azure_endpoint", "api_key", "http_client", "http_async_client"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # Environment variable fallbacks (DRY pattern)
        for kwarg_name, env_var in {
            "azure_endpoint": "AZURE_OPENAI_ENDPOINT",
            "api_key": "AZURE_OPENAI_API_KEY",
        }.items():
            if kwarg_name not in llm_kwargs:
                value = os.environ.get(env_var)
                if value:
                    llm_kwargs[kwarg_name] = value

        if "api_version" not in llm_kwargs:
            api_version = os.environ.get("OPENAI_API_VERSION", "2024-02-15-preview")
            llm_kwargs["api_version"] = api_version

        return AzureChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate Azure deployment name (always valid, Azure validates at runtime)."""
        return bool(self.deployment_name)
