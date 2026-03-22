from typing import Any, Optional

from langchain_aws import ChatBedrockConverse

from .base_client import BaseLLMClient
from .validators import validate_model


class BedrockClient(BaseLLMClient):
    """Client for Amazon Bedrock models (Claude, Kimi, Qwen, GLM, etc.)."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatBedrockConverse instance."""
        llm_kwargs = {"model_id": self.model}

        if "region_name" in self.kwargs:
            llm_kwargs["region_name"] = self.kwargs["region_name"]
        if "max_tokens" in self.kwargs:
            llm_kwargs["max_tokens"] = self.kwargs["max_tokens"]
        if "callbacks" in self.kwargs:
            llm_kwargs["callbacks"] = self.kwargs["callbacks"]
        if "timeout" in self.kwargs:
            llm_kwargs["timeout"] = self.kwargs["timeout"]

        return ChatBedrockConverse(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Bedrock (pass-through, model IDs are flexible)."""
        return True
