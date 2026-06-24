"""Fallback LLM client that chains multiple providers.

Tries the primary provider first. On any failure (rate limit, auth error,
server error, timeout), falls back to the secondary provider. This follows
the same pattern as the data vendor fallback in ``dataflows/interface.py``
but for LLM providers.

Usage in config::

    llm_provider = "openai"
    llm_fallback_provider = "puter"
"""

from __future__ import annotations

import logging
from typing import Any

from .base_client import BaseLLMClient

logger = logging.getLogger(__name__)


class FallbackLLMClient(BaseLLMClient):
    """Client that wraps a primary and fallback LLM client.

    ``get_llm()`` returns a ``FallbackChatLLM`` that tries the primary
    provider first and falls back to the secondary on failure.
    """

    def __init__(
        self,
        primary: BaseLLMClient,
        fallback: BaseLLMClient,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def get_llm(self) -> FallbackChatLLM:
        return FallbackChatLLM(
            self._primary.get_llm(),
            self._fallback.get_llm(),
        )

    def validate_model(self) -> bool:
        return self._primary.validate_model() or self._fallback.validate_model()

    def get_provider_name(self) -> str:
        return f"{self._primary.get_provider_name()}+{self._fallback.get_provider_name()}"

    @property
    def model(self) -> str:
        return self._primary.model

    @model.setter
    def model(self, value: str) -> None:
        self._primary.model = value
        self._fallback.model = value


class FallbackChatLLM:
    """Wraps two LLM (or Runnable) instances, trying primary first,
    falling back to secondary on any exception.

    Supports ``invoke``, ``with_structured_output``, and ``bind_tools``
    so it can be used anywhere a plain langchain Chat model is expected
    in the TradingAgents pipeline.
    """

    def __init__(self, primary: Any, fallback: Any) -> None:
        object.__setattr__(self, "_primary", primary)
        object.__setattr__(self, "_fallback", fallback)

    # -- Core LLM methods ------------------------------------------------

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        try:
            return self._primary.invoke(input, config, **kwargs)
        except Exception as exc:
            logger.warning(
                "Primary LLM failed (%s: %s); falling back to secondary",
                type(exc).__name__, exc,
            )
            return self._fallback.invoke(input, config, **kwargs)

    def with_structured_output(self, schema: Any, *, method: Any = None, **kwargs: Any) -> FallbackChatLLM:
        primary_structured: Any = None
        fallback_structured: Any = None

        try:
            primary_structured = self._primary.with_structured_output(
                schema, method=method, **kwargs
            )
        except Exception as exc:
            logger.debug(
                "Primary LLM with_structured_output failed (%s); "
                "trying secondary",
                exc,
            )

        try:
            fallback_structured = self._fallback.with_structured_output(
                schema, method=method, **kwargs
            )
        except Exception as exc:
            logger.debug(
                "Secondary LLM with_structured_output failed (%s)",
                exc,
            )

        if primary_structured is not None and fallback_structured is not None:
            return FallbackChatLLM(primary_structured, fallback_structured)
        if primary_structured is not None:
            return primary_structured
        if fallback_structured is not None:
            return fallback_structured
        raise NotImplementedError(
            f"Neither primary nor secondary LLM supports "
            f"with_structured_output for schema {schema}"
        )

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> FallbackChatLLM:
        primary_bound: Any = None
        fallback_bound: Any = None

        try:
            primary_bound = self._primary.bind_tools(tools, **kwargs)
        except Exception as exc:
            logger.debug(
                "Primary LLM bind_tools failed (%s); trying secondary",
                exc,
            )

        try:
            fallback_bound = self._fallback.bind_tools(tools, **kwargs)
        except Exception as exc:
            logger.debug(
                "Secondary LLM bind_tools failed (%s)",
                exc,
            )

        if primary_bound is not None and fallback_bound is not None:
            return FallbackChatLLM(primary_bound, fallback_bound)
        if primary_bound is not None:
            return primary_bound
        if fallback_bound is not None:
            return fallback_bound
        raise NotImplementedError(
            "Neither primary nor secondary LLM supports bind_tools"
        )

    # -- Attribute passthrough -------------------------------------------

    def __getattr__(self, name: str) -> Any:
        return getattr(self._primary, name)
