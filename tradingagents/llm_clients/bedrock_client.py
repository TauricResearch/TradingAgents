import os
import warnings
from typing import Any, Optional

from langchain_aws import ChatBedrockConverse

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

_PASSTHROUGH_KWARGS = ("timeout", "max_retries", "callbacks", "max_tokens", "temperature")


class NormalizedChatBedrockConverse(ChatBedrockConverse):
    """ChatBedrockConverse with normalized content output."""

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))


class BedrockClient(BaseLLMClient):
    """Client for AWS Bedrock models via the Converse API.

    Authentication uses the standard boto3 credential chain.
    Only AWS_BEDROCK_REGION (default: us-east-1) and optionally
    AWS_PROFILE are explicitly read.
    """

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()

        # Warn if model doesn't look like a Bedrock model ID
        if "." not in self.model and not self.model.startswith("arn:"):
            warnings.warn(
                f"Model '{self.model}' doesn't look like a Bedrock model ID "
                f"(expected format: 'provider.model-name' or an ARN). "
                f"Did you forget to update config['deep_think_llm']?",
                RuntimeWarning,
                stacklevel=2,
            )

        region = os.environ.get("AWS_BEDROCK_REGION", "us-east-1")

        llm_kwargs: dict[str, Any] = {
            "model_id": self.model,
            "region_name": region,
        }

        if self.base_url:
            llm_kwargs["endpoint_url"] = self.base_url

        profile = os.environ.get("AWS_PROFILE")
        if profile:
            llm_kwargs["credentials_profile_name"] = profile

        # Auto-enable adaptive thinking for Opus 4.7
        if "opus-4-7" in self.model:
            llm_kwargs["additional_model_request_fields"] = {
                "thinking": {"type": "adaptive"}
            }

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        try:
            return NormalizedChatBedrockConverse(**llm_kwargs)
        except Exception as e:
            if "credential" in str(e).lower():
                raise ValueError(
                    "AWS Bedrock: No valid credentials found. Configure one of:\n"
                    "  1. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY env vars\n"
                    "  2. Set AWS_PROFILE to use a named profile\n"
                    "  3. Run on EC2/ECS/Lambda with an IAM role attached\n"
                    "  4. Run `aws sso login` for SSO-based authentication\n"
                    f"Original error: {e}"
                ) from e
            raise

    def validate_model(self) -> bool:
        return validate_model("bedrock", self.model)
