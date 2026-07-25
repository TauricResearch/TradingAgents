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
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from tradingagents.observability.errors import ObservationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Any | None:
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


def _invoke_structured_pair(
    structured_llm: Any | None,
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> tuple[str, T | None]:
    """Run the structured call and render to markdown; fall back to free-text.

    Returns the rendered text and, when the structured path succeeded, the
    parsed object.  The object is ``None`` on the free-text fallback so a
    caller can decide whether a public scorecard is available to persist.
    """
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            if result is None:
                # A thinking model can answer in plain text instead of calling
                # the tool, leaving the parser with nothing to return. Treat it
                # as a structured miss and fall back, with a clear reason.
                raise ValueError("structured output returned no parsed result")
            return render(result), result
        except (ObservationError, AssertionError):
            raise
        except Exception as exc:
            logger.warning(
                "%s: structured-output invocation failed (%s); retrying once as free text",
                agent_name, exc,
            )

    response = plain_llm.invoke(prompt)
    return response.content, None


def invoke_structured_or_freetext(
    structured_llm: Any | None,
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> str:
    """Run the structured call and render to markdown; fall back to free-text on any failure.

    ``prompt`` is whatever the underlying LLM accepts (a string for chat
    invocations, a list of message dicts for chat models that take that
    shape). The same value is forwarded to the free-text path so the
    fallback sees the same input the structured call did.
    """
    return _invoke_structured_pair(
        structured_llm, plain_llm, prompt, render, agent_name
    )[0]


def invoke_structured_or_freetext_with_artifact(
    structured_llm: Any | None,
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> tuple[str, T | None]:
    """Like :func:`invoke_structured_or_freetext` but also return the parsed object.

    The object is ``None`` on the free-text fallback path or when a thinking
    model returned no parsed result.  Use this when the caller needs the typed
    instance to persist a public scorecard; use the original function when only
    the rendered text is needed.
    """
    return _invoke_structured_pair(
        structured_llm, plain_llm, prompt, render, agent_name
    )
