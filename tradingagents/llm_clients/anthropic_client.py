import logging
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

logger = logging.getLogger(__name__)

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "max_tokens",
    "callbacks", "http_client", "http_async_client", "effort",
)


def _format_prompt(input_) -> str:
    """Format LangChain invoke input into a readable prompt string."""
    if isinstance(input_, str):
        return input_

    if isinstance(input_, list):
        lines: list[str] = []
        for msg in input_:
            if isinstance(msg, BaseMessage):
                role = msg.__class__.__name__.replace("Message", "").upper()
                lines.append(f"[{role}]\n{msg.content}")
            elif isinstance(msg, dict):
                role = msg.get("role", "unknown").upper()
                lines.append(f"[{role}]\n{msg.get('content', '')}")
            else:
                lines.append(str(msg))
        return "\n\n".join(lines)

    if isinstance(input_, dict):
        messages = input_.get("messages", [])
        return _format_prompt(messages)

    return str(input_)


class NormalizedChatAnthropic(ChatAnthropic):
    """ChatAnthropic with prompt logging and normalized content output."""

    def invoke(self, input, config=None, **kwargs):
        prompt_str = _format_prompt(input)
        logger.info(
            "\n%s\n[CLAUDE PROMPT]\n%s\n%s",
            "=" * 72,
            prompt_str,
            "=" * 72,
        )
        return normalize_content(super().invoke(input, config, **kwargs))


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude models."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatAnthropic instance."""
        llm_kwargs = {"model": self.model}

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return NormalizedChatAnthropic(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Anthropic."""
        return validate_model("anthropic", self.model)
