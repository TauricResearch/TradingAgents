"""Structured output utility with graceful fallback to free-text extraction."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from tradingagents.agents.utils.llm_guard import invoke_with_timeout, resolve_timeout

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


def invoke_structured_or_freetext(  # noqa: UP047
    llm: Any,
    schema: type[T],
    messages: list,
    fallback_extractor: Callable[[str], dict[str, Any]],
    *,
    agent_name: str = "unknown",
    timeout_tier: str = "deep",
    max_tokens: int | None = None,
) -> tuple[T | None, str, dict[str, Any] | None]:
    """Attempt structured output, fall back to free-text extraction on failure.

    Returns:
        Tuple of (schema_instance_or_None, raw_text_content, fallback_dict_or_None).
        Exactly one of schema_instance or fallback_dict will be non-None.
    """
    timeout_seconds = resolve_timeout(timeout_tier)

    # Try structured output first
    try:
        structured_llm = llm.with_structured_output(schema)
        result, error = invoke_with_timeout(
            structured_llm, messages, timeout_seconds=timeout_seconds, max_tokens=max_tokens
        )
        if error is None and result is not None:
            # result is already a Pydantic model instance
            return result, "", None
        if error is not None:
            raise error
    except (NotImplementedError, ValidationError, TypeError, AttributeError) as exc:
        logger.warning(
            "%s: structured output failed (%s: %s), falling back to free-text",
            agent_name,
            type(exc).__name__,
            str(exc)[:200],
        )
    except Exception as exc:
        logger.warning(
            "%s: structured output unexpected error (%s: %s), falling back to free-text",
            agent_name,
            type(exc).__name__,
            str(exc)[:200],
        )

    # Fallback: invoke without structured output, then extract
    result, error = invoke_with_timeout(
        llm, messages, timeout_seconds=timeout_seconds, max_tokens=max_tokens
    )
    if error is not None:
        if isinstance(error, TimeoutError):
            raise error
        raise RuntimeError(f"{agent_name}: fallback invocation failed: {error}") from error

    raw_text = result.content if result else ""
    fallback_dict = fallback_extractor(raw_text)
    return None, raw_text, fallback_dict
