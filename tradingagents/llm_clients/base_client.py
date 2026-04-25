import re
from abc import ABC, abstractmethod
from typing import Any

# Matches <think>...</think> blocks used by DeepSeek R1, Qwen QwQ, kimi-k2.5,
# and other reasoning models served via OpenAI-compatible chat completions.
# The alternation (?:</think>|$) handles both properly closed blocks and
# token-budget-truncated blocks where </think> was never emitted.
# Note: also strips literal "<think>" mentions in visible prose — accepted
# tradeoff since empty/raw scratchpad output is far worse.
# Only applies to responses routed through BaseLLMClient subclasses.
_THINK_RE = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL)


def normalize_content(response: Any) -> Any:
    """Normalize LLM response content to a plain string.

    Handles two formats:
    - List of typed blocks (OpenAI Responses API, Google): extracts text blocks,
      discards reasoning/metadata blocks.
    - Plain string with inline <think>...</think> scratchpad (DeepSeek R1, kimi,
      QwQ via OpenRouter): strips the thinking block, keeps visible output only.
    """
    content = response.content
    if isinstance(content, list):
        texts = [
            item.get("text", "")
            if isinstance(item, dict) and item.get("type") == "text"
            else item
            if isinstance(item, str)
            else ""
            for item in content
        ]
        response.content = "\n".join(t for t in texts if t)
    elif isinstance(content, str):
        response.content = _THINK_RE.sub("", content).strip()
    return response


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, model: str, base_url: str | None = None, **kwargs: Any):
        self.model = model
        self.base_url = base_url
        self.kwargs = kwargs

    @abstractmethod
    def get_llm(self) -> Any:
        """Return the configured LLM instance."""
        pass

    @abstractmethod
    def validate_model(self) -> bool:
        """Validate that the model is supported by this client."""
        pass
