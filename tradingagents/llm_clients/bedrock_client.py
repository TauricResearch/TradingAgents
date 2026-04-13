from typing import Any, Optional

from botocore.config import Config as BotoConfig
from langchain_aws import ChatBedrockConverse

from .base_client import BaseLLMClient, normalize_content

_BEDROCK_MODELS = [
    "us.anthropic.claude-sonnet-4-6",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-opus-4-6-v1",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
]

_PASSTHROUGH_KWARGS = (
    "region_name",
    "credentials_profile_name",
    "max_tokens",
    "temperature",
    "callbacks",
)


class NormalizedChatBedrockConverse(ChatBedrockConverse):
    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))


class BedrockClient(BaseLLMClient):
    """Client for Amazon Bedrock models via ChatBedrockConverse."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        llm_kwargs = {
            "model_id": self.model,
            "config": BotoConfig(read_timeout=300, retries={"max_attempts": 3}),
        }
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]
        if "region_name" not in llm_kwargs:
            llm_kwargs["region_name"] = "us-east-1"
        return NormalizedChatBedrockConverse(**llm_kwargs)

    def validate_model(self) -> bool:
        return self.model in _BEDROCK_MODELS
