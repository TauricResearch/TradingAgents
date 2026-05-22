"""Shared helpers for invoking an agent with structured output and a graceful fallback.

The Portfolio Manager, Trader, and Research Manager all follow the same
canonical pattern:

1. At agent creation, wrap the LLM with ``with_structured_output(Schema)``
   so the model returns a typed Pydantic instance. If the provider does
   not support structured output (rare; mostly older Ollama models), the
   wrap is skipped and the agent uses free-text generation instead.
2. At invocation, run the structured call and render the result back to
   markdown. If the structured call itself fails for any reason
   (malformed JSON from a weak model, transient provider issue), fall
   back to a plain ``llm.invoke`` so the pipeline never blocks.

Centralising the pattern here keeps the agent factories small and ensures
all three agents log the same warnings when fallback fires.
"""

from __future__ import annotations

import logging
import json
from collections.abc import MutableMapping
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _normalise_prompt_for_cache(prompt: Any) -> str:
    """Return a deterministic string key for common LLM prompt shapes."""
    try:
        return json.dumps(prompt, sort_keys=True, default=str, ensure_ascii=False)
    except TypeError:
        return repr(prompt)


def _cache_key(agent_name: str, mode: str, prompt: Any) -> str:
    return f"{agent_name}:{mode}:{_normalise_prompt_for_cache(prompt)}"


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Optional[Any]:
    """Return ``llm.with_structured_output(schema)`` or ``None`` if unsupported.

    Logs a warning when the binding fails so the user understands the agent
    will use free-text generation for every call instead of one-shot fallback.
    """
    try:
        return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError) as exc:
        logger.warning(
            "%s: provider does not support with_structured_output (%s); "
            "falling back to free-text generation",
            agent_name, exc,
        )
        return None


def invoke_structured_or_freetext(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
    cache: Optional[MutableMapping[str, str]] = None,
) -> str:
    """Run the structured call and render to markdown; fall back to free-text on any failure.

    ``prompt`` is whatever the underlying LLM accepts (a string for chat
    invocations, a list of message dicts for chat models that take that
    shape). The same value is forwarded to the free-text path so the
    fallback sees the same input the structured call did.
    """
    freetext_key = _cache_key(agent_name, "freetext", prompt)
    if cache is not None and freetext_key in cache:
        return cache[freetext_key]

    if structured_llm is not None:
        key = _cache_key(agent_name, "structured", prompt)
        if cache is not None and key in cache:
            return cache[key]
        try:
            result = structured_llm.invoke(prompt)
            rendered = render(result)
            if cache is not None:
                cache[key] = rendered
            return rendered
        except Exception as exc:
            logger.warning(
                "%s: structured-output invocation failed (%s); retrying once as free text",
                agent_name, exc,
            )

    response = plain_llm.invoke(prompt)
    content = response.content
    if cache is not None:
        cache[freetext_key] = content
    return content
