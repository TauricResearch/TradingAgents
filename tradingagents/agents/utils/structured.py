"""Shared helpers for invoking an agent with structured output and a graceful fallback.

The Portfolio Manager, Trader, and Research Manager all follow the same
canonical pattern:

1. At agent creation, wrap the LLM with ``with_structured_output(Schema)``
   so the model returns a typed Pydantic instance. If the provider does
   not support structured output (rare; mostly older Ollama models), the
   wrap is skipped and the agent uses free-text generation instead.
2. At invocation, run the structured call and render the result back to
   markdown. Output-shape failures get one plain-text fallback. Provider
   availability failures propagate because a second request cannot repair
   authentication, throttling, or a network outage.

Centralising the pattern here keeps the agent factories small and ensures
all three agents log the same warnings when fallback fires.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from json import JSONDecodeError
from typing import Any, TypeVar

from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, ValidationError

from tradingagents.logging_utils import safe_exception_type

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Schema-only structured output binds exactly one tool (the schema itself), so a
# model that reaches for a search tool emits an unknown tool call and the whole
# structured attempt is discarded for a free-text retry. Agents on this path
# state the constraint explicitly rather than relying on the binding alone
# (#1130).
NO_EXTERNAL_TOOLS = (
    "Use only the evidence provided in this prompt. Do not call external tools "
    "or search the web; if something is missing, say so explicitly."
)

_PARSE_ERRORS = (
    OutputParserException,
    ValidationError,
    JSONDecodeError,
    NotImplementedError,
)


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Any | None:
    """Return ``llm.with_structured_output(schema)`` or ``None`` if unsupported.

    Logs an informational event when binding fails so the user understands the agent
    will use free-text generation for every call instead of one-shot fallback.
    """
    binder = getattr(llm, "with_structured_output", None)
    if binder is None:
        logger.info(
            "%s: provider does not support with_structured_output; "
            "falling back to free-text generation",
            agent_name,
        )
        return None
    try:
        return binder(schema)
    except NotImplementedError as exc:
        logger.info(
            "%s: provider does not support with_structured_output (%s); "
            "falling back to free-text generation",
            agent_name, safe_exception_type(exc),
        )
        return None


def invoke_structured_or_freetext(
    structured_llm: Any | None,
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> str:
    """Render structured output, with one fallback for output-shape failures.

    ``prompt`` is whatever the underlying LLM accepts (a string for chat
    invocations, a list of message dicts for chat models that take that
    shape). The same value is forwarded to the free-text path so the
    fallback sees the same input the structured call did.
    """
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
        except _PARSE_ERRORS as exc:
            logger.info(
                "%s: structured-output invocation failed (%s); retrying once as free text",
                agent_name, safe_exception_type(exc),
            )
        else:
            if result is not None:
                return render(result)
            logger.info(
                "%s: structured output returned no parsed result; "
                "retrying once as free text",
                agent_name,
            )

    response = plain_llm.invoke(prompt)
    return response.content
