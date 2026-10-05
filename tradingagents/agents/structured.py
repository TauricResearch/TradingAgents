"""Shared helpers for invoking an agent with structured output and a graceful fallback.

The Portfolio Manager, Trader, and Research Manager all follow the same
canonical pattern:

1. At agent creation, wrap the LLM with ``with_structured_output(Schema)``
   so the model returns a typed Pydantic instance. If the provider does
   not support structured output (rare; mostly older Ollama models), the
   wrap is skipped and the agent uses free-text generation instead.
2. At invocation, run the structured call and render the result back to
   markdown. A ``None`` parse (the model answered in plain text instead of
   calling the schema tool) is retried once — it is a sampling miss, and a
   single retry usually recovers the schema (#1390). If the structured call
   still fails after that (or fails outright with a provider error), fall
   back to a plain ``llm.invoke`` so the pipeline never blocks.

Centralising the pattern here keeps the agent factories small and ensures
all three agents log the same warnings when fallback fires.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

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


def invoke_structured(structured_llm: Any | None, prompt: Any, agent_name: str) -> T | None:
    """Run the structured call; ``None`` when there is none or it fails.

    ``prompt`` is whatever the underlying LLM accepts (a string for chat
    invocations, a list of message dicts for chat models that take that
    shape), so a caller can forward the same value to its free-text fallback.

    A ``None`` parsed result is a sampling miss, not a provider failure:
    thinking models periodically answer in plain text instead of calling the
    bound schema tool (~1x per run in the #1390 measurements, with no
    ``tool_choice`` errors at all). A single same-prompt retry recovers the
    schema far more often than not, so it is tried before giving up. Hard
    provider errors are not retried — the fallback remains one attempt away.
    """
    if structured_llm is None:
        return None
    for attempt in range(2):
        try:
            result = structured_llm.invoke(prompt)
            if result is None:
                # A thinking model answered in plain text instead of calling
                # the tool, leaving the parser with nothing to return. On the
                # first attempt only, retry the same structured call: the miss
                # is a sampling artifact and a retry often recovers the schema
                # (#1390). On the second, fall back to free text below.
                if attempt == 0:
                    logger.info(
                        "%s: structured output returned no parsed result; "
                        "retrying the structured call once (#1390)",
                        agent_name,
                    )
                    continue
                logger.warning(
                    "%s: structured-output invocation failed "
                    "(no parsed result after retry); retrying once as free text",
                    agent_name,
                )
                return None
            return result
        except Exception as exc:
            logger.warning(
                "%s: structured-output invocation failed (%s); retrying once as free text",
                agent_name, exc,
            )
            return None
    return None


def invoke_structured_or_freetext(
    structured_llm: Any | None,
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> str:
    """Run the structured call and render to markdown; fall back to free-text on any failure."""
    result = invoke_structured(structured_llm, prompt, agent_name)
    if result is not None:
        return render(result)
    return plain_llm.invoke(prompt).content
