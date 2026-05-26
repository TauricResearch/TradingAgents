import os
from typing import Any, Optional

try:
    from langchain_aws import ChatBedrockConverse
except ImportError:
    raise ImportError(
        "Could not import langchain-aws. Please install it using 'pip install .[bedrock]' "
        "to use the AWS Bedrock provider."
    )

from .base_client import BaseLLMClient, normalize_content

_PASSTHROUGH_KWARGS = ("timeout", "max_retries", "callbacks")


class NormalizedChatBedrockConverse(ChatBedrockConverse):
    """ChatBedrockConverse with normalized content output."""

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

    async def ainvoke(self, input, config=None, **kwargs):
        return normalize_content(await super().ainvoke(input, config, **kwargs))

    def with_structured_output(self, schema, *, method=None, **kwargs):
        method = method or "function_calling"
        return super().with_structured_output(schema, method=method, **kwargs)


class BedrockClient(BaseLLMClient):
    """Client for AWS Bedrock via the Converse API.

    Uses the standard AWS credential chain for authentication:
        - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        - Shared credentials file (~/.aws/credentials)
        - IAM role (EC2, ECS, Lambda)

    Optional environment variables:
        AWS_PROFILE: Named profile in ~/.aws/credentials
        AWS_REGION / AWS_DEFAULT_REGION: AWS region (default: us-west-2)
    """

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatBedrockConverse instance."""
        import boto3
        from botocore.config import Config

        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-west-2"
        profile = os.environ.get("AWS_PROFILE")

        session = boto3.Session(profile_name=profile, region_name=region)
        client = session.client(
            "bedrock-runtime",
            config=Config(
                read_timeout=300,
                connect_timeout=10,
                retries={"max_attempts": 3},
            ),
        )

        llm_kwargs: dict[str, Any] = {
            "model": self.model,
            "region_name": region,
            "client": client,
        }

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return NormalizedChatBedrockConverse(**llm_kwargs)

    def validate_model(self) -> bool:
        """Bedrock accepts any model/inference-profile ID."""
        return True
