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

----

**Anthropic extended-thinking compatibility**

Claude models served via Anthropic's API (directly or proxied through
GitHub Copilot's OpenAI-compatible endpoint) reject any request that
combines ``extended_thinking`` with a forced ``tool_choice``. Structured
output via LangChain imposes ``tool_choice="any"`` to guarantee the model
emits the schema, so the two features are mutually exclusive at the
provider level — every structured call from a thinking-enabled Claude
fails with::

    400 - Thinking may not be enabled when tool_choice forces tool use.

To preserve the structured plan (rather than silently degrading to free
text), we detect this combination at bind time and build a *non-thinking
twin* of the LLM specifically for structured calls. The original
thinking-enabled LLM remains in use for everything else.

The twin is built by copying the LLM with a model id that omits the
effort suffix (``claude-opus-4.7-xhigh`` → ``claude-opus-4.7``). For
direct ``ChatAnthropic`` instances we drop the ``thinking`` kwarg
instead. If neither path applies we fall through to the original
behaviour.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# Effort suffixes Copilot encodes into Claude model ids. Order matters: we
# strip the longest match first so ``claude-opus-4.7-xhigh`` doesn't get
# truncated to ``claude-opus-4.7-x``.
_THINKING_SUFFIXES = ("-xhigh", "-high", "-medium", "-low", "-minimal")

_THINKING_SUFFIX_RE = re.compile(
    r"-(?:xhigh|high|medium|low|minimal)$",
    flags=re.IGNORECASE,
)


def _strip_thinking_suffix(model_name: str) -> str:
    """Return ``model_name`` with any trailing effort suffix removed.

    ``claude-opus-4.7-xhigh`` → ``claude-opus-4.7``. Returns the input
    unchanged when no recognised suffix is present.
    """
    if not isinstance(model_name, str):
        return model_name
    return _THINKING_SUFFIX_RE.sub("", model_name)


def _build_structured_twin(llm: Any) -> Any:
    """Return a copy of ``llm`` configured to accept forced ``tool_choice``.

    For Claude models served via Copilot (``ChatOpenAI`` with a
    ``claude-*-{effort}`` model id) the twin uses the same model with the
    effort suffix stripped, which causes Copilot to omit the
    ``extended_thinking`` flag when proxying to Anthropic.

    For direct ``ChatAnthropic`` instances the twin drops the ``thinking``
    kwarg if present.

    Returns the original LLM unchanged if no remediation applies.
    """
    model_attr = getattr(llm, "model_name", None) or getattr(llm, "model", None)
    if not isinstance(model_attr, str):
        return llm

    is_claude = "claude" in model_attr.lower()
    if not is_claude:
        return llm

    stripped = _strip_thinking_suffix(model_attr)
    if stripped == model_attr:
        # No effort suffix — assume thinking isn't forced on, leave LLM alone.
        return llm

    # pydantic v2 models expose ``model_copy``; LangChain LLMs are pydantic
    # BaseModels so this works for both ChatOpenAI and ChatAnthropic.
    try:
        # ChatOpenAI uses ``model_name``; ChatAnthropic uses ``model``. Update
        # whichever attribute the underlying LLM uses.
        update_field = "model_name" if hasattr(llm, "model_name") else "model"
        twin = llm.model_copy(update={update_field: stripped})
        logger.info(
            "Structured-output twin built for thinking-enabled Claude: %s -> %s",
            model_attr, stripped,
        )
        return twin
    except Exception as exc:  # noqa: BLE001 — fail-open to original LLM
        logger.warning(
            "Failed to build non-thinking twin for %s (%s); structured output "
            "will likely fall back to free text on Anthropic provider.",
            model_attr, exc,
        )
        return llm


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Optional[Any]:
    """Return ``llm.with_structured_output(schema)`` or ``None`` if unsupported.

    For thinking-enabled Claude models, transparently builds a
    non-thinking twin so structured output works (see module docstring).

    Logs a warning when the binding fails so the user understands the agent
    will use free-text generation for every call instead of one-shot fallback.
    """
    target = _build_structured_twin(llm)
    try:
        return target.with_structured_output(schema)
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
) -> str:
    """Run the structured call and render to markdown; fall back to free-text on any failure.

    ``prompt`` is whatever the underlying LLM accepts (a string for chat
    invocations, a list of message dicts for chat models that take that
    shape). The same value is forwarded to the free-text path so the
    fallback sees the same input the structured call did.
    """
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            return render(result)
        except Exception as exc:
            logger.warning(
                "%s: structured-output invocation failed (%s); retrying once as free text",
                agent_name, exc,
            )

    response = plain_llm.invoke(prompt)
    return response.content
