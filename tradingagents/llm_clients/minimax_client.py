"""MiniMax LLM client for TradingAgents.

Uses LangChain's built-in MiniMaxChatOpenAI which handles
MiniMax's non-standard /chatcompletion_v2 endpoint automatically.
"""

from typing import Any, Optional

from langchain_community.chat_models.minimax import MiniMaxChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


class MiniMaxClient(BaseLLMClient):
    """TradingAgents LLM client for MiniMax.

    Leverages LangChain's MiniMaxChatOpenAI which already knows how to
    route requests to MiniMax's API at /chatcompletion_v2.
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self._model = model

    def get_llm(self) -> Any:
        """Return configured MiniMaxChatOpenAI instance."""
        return MiniMaxChatOpenAI(model=self._model)

    def validate_model(self) -> bool:
        """Validate model for MiniMax (accepts any model name)."""
        return True
