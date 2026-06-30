import os
from typing import Any

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

# Bedrock has no global default region; us-west-2 hosts the broadest model set.
_DEFAULT_REGION = "us-west-2"
_BEDROCK_CLASS = None


def _bedrock_class():
    """Lazily import langchain-aws (the optional ``[bedrock]`` extra) and return a
    ChatBedrockConverse subclass with normalized content output.

    Imported on demand so the optional dependency (and boto3) isn't required by
    the rest of the package; cached after the first call.
    """
    global _BEDROCK_CLASS
    if _BEDROCK_CLASS is not None:
        return _BEDROCK_CLASS

    try:
        from langchain_aws import ChatBedrockConverse
    except ImportError as exc:
        raise ImportError(
            "AWS Bedrock support requires the optional 'langchain-aws' dependency. "
            'Install it with: pip install "tradingagents[bedrock]"'
        ) from exc

    class NormalizedChatBedrockConverse(ChatBedrockConverse):
        """ChatBedrockConverse with normalized (string) content output."""

        def invoke(self, input, config=None, **kwargs):
            return normalize_content(super().invoke(input, config, **kwargs))

    _BEDROCK_CLASS = NormalizedChatBedrockConverse
    return _BEDROCK_CLASS


class BedrockClient(BaseLLMClient):
    """Client for Amazon Bedrock via the Converse API (langchain-aws).

    Two authentication modes are supported, in this precedence (matching
    botocore's own per-client resolution):

    1. **Bedrock API key (bearer token)** — set ``AWS_BEARER_TOKEN_BEDROCK`` to a
       Bedrock API key (created in the AWS console / via IAM). langchain-aws reads
       it automatically and sends ``Authorization: Bearer <token>`` instead of
       SigV4, so no AWS access key, secret, or profile is needed. This is the
       simplest setup for a single-account run.
    2. **AWS SigV4 credential chain** — the standard chain (env access keys,
       ``~/.aws/credentials``, ``AWS_PROFILE``, or an IAM role) when no bearer
       token is set.

    Either way an explicit region is required (the bearer token carries none):
    set ``AWS_REGION`` / ``AWS_DEFAULT_REGION`` (otherwise this falls back to
    ``us-west-2``). The model name is a Bedrock model ID or cross-region
    inference profile ID, e.g. ``us.anthropic.claude-opus-4-8-v1:0``.
    """

    def get_llm(self) -> Any:
        """Return a configured ChatBedrockConverse instance."""
        self.warn_if_unknown_model()
        chat_cls = _bedrock_class()

        region = (
            os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or _DEFAULT_REGION
        )
        llm_kwargs = {"model": self.model, "region_name": region}
        for key in ("temperature", "max_tokens", "max_retries", "callbacks"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]
        return chat_cls(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Bedrock (any model ID accepted)."""
        return validate_model("bedrock", self.model)
