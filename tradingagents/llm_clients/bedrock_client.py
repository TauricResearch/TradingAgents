from typing import Any, Optional

from langchain_aws import ChatBedrockConverse

from .base_client import BaseLLMClient


class BedrockClient(BaseLLMClient):
    """Client for Amazon Bedrock models.

    Supports any model available on Bedrock via IAM Role (no API key needed),
    including Claude, Amazon Nova, Kimi, Qwen, GLM, DeepSeek, MiniMax, and more.

    Authentication:
        Uses boto3 default credential chain: IAM Role (EC2/Lambda), environment
        variables (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY), or ~/.aws/credentials.

    Model ID formats:
        - Cross-region inference profile (recommended):
            ``us.anthropic.claude-haiku-4-5-20251001-v1:0``
            ``eu.anthropic.claude-3-5-sonnet-20240620-v1:0``
        - Direct on-demand (us-east-1 default region only):
            ``amazon.nova-lite-v1:0``
            ``moonshotai.kimi-k2.5``
            ``qwen.qwen3-32b-v1:0``
            ``zai.glm-4.7-flash``
            ``deepseek.v3.2``

    Note:
        When specifying a non-default ``region_name``, use region-specific
        inference profile IDs (e.g. ``us-west-2.anthropic.claude-...``),
        as direct model IDs only support on-demand throughput in us-east-1.

    Example::

        config["llm_provider"]    = "bedrock"
        config["deep_think_llm"]  = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        config["quick_think_llm"] = "amazon.nova-micro-v1:0"
    """

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatBedrockConverse instance."""
        llm_kwargs: dict = {"model_id": self.model}

        for key in ("region_name", "max_tokens", "callbacks", "timeout"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return ChatBedrockConverse(**llm_kwargs)

    def validate_model(self) -> bool:
        """Bedrock model IDs are dynamic; skip static validation."""
        return True
