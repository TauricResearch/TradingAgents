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

**Pydantic-AI backend (optional):** when ``TRADINGAGENTS_USE_PYDANTIC_AI=1``
is set, the structured call is routed through a pydantic-ai ``Agent`` whose
``output_type`` is the target schema. Pydantic-AI retries on validation
failure (the model is prompted to correct its output) instead of falling
through to free text on the first malformed response — preserving the
structured signal (BUY/SELL/HOLD, rating) that downstream parsers rely on.
The fallback to ``plain_llm.invoke`` remains as a last resort.
"""

from __future__ import annotations

import logging
import os
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

_USE_PYDANTIC_AI = os.environ.get("TRADINGAGENTS_USE_PYDANTIC_AI", "").lower() in (
    "1",
    "true",
    "yes",
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
            agent_name,
            exc,
        )
        return None


def _invoke_via_pydantic_ai(
    schema: type[T],
    prompt: Any,
    instructions: str,
    agent_name: str,
) -> T | None:
    """Run the prompt through a pydantic-ai Agent with typed output + retry.

    Returns the validated Pydantic instance, or ``None`` if pydantic-ai
    itself fails (so the caller can fall back to the legacy path).
    """
    if not _USE_PYDANTIC_AI:
        return None
    try:
        from tradingagents.llm_clients.proxy_clients import make_pydantic_ai_agent

        agent = make_pydantic_ai_agent(
            output_type=schema,
            instructions=instructions,
        )
        # Normalize LangChain message dicts / strings into a single prompt string.
        if isinstance(prompt, list):
            parts = []
            for msg in prompt:
                content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                parts.append(content)
            prompt_str = "\n\n".join(parts)
        else:
            prompt_str = str(prompt)
        result = agent.run_sync(prompt_str)
        return result.output
    except Exception as exc:
        logger.warning(
            "%s: pydantic-ai backend failed (%s); falling back to legacy path",
            agent_name,
            exc,
        )
        return None


def invoke_structured_or_freetext(
    structured_llm: Any | None,
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
    schema: type[T] | None = None,
    instructions: str = "",
) -> str:
    """Run the structured call and render to markdown; fall back to free-text on any failure.

    ``prompt`` is whatever the underlying LLM accepts (a string for chat
    invocations, a list of message dicts for chat models that take that
    shape). The same value is forwarded to the free-text path so the
    fallback sees the same input the structured call did.

    When the pydantic-ai backend is enabled (``TRADINGAGENTS_USE_PYDANTIC_AI=1``)
    and ``schema`` is provided, the call routes through pydantic-ai first —
    gaining a validation-retry loop that the legacy one-shot path lacks.
    """
    # Pydantic-AI backend: validation-retry loop before falling back.
    if _USE_PYDANTIC_AI and schema is not None:
        result = _invoke_via_pydantic_ai(schema, prompt, instructions, agent_name)
        if result is not None:
            return render(result)

    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            if result is None:
                # A thinking model can answer in plain text instead of calling
                # the tool, leaving the parser with nothing to return. Treat it
                # as a structured miss and fall back, with a clear reason.
                raise ValueError("structured output returned no parsed result")
            return render(result)
        except Exception as exc:
            logger.warning(
                "%s: structured-output invocation failed (%s); retrying once as free text",
                agent_name,
                exc,
            )

    response = plain_llm.invoke(prompt)
    return response.content
