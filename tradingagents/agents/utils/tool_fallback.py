"""Graceful tool-binding for providers that run their own tool loop.

The market, news, and fundamentals analysts normally let the LLM call
LangChain tools to fetch the data they reason over. Chat-only providers —
notably the codex CLI adapter, which runs its OWN internal tool-use loop
and refuses external LangChain tool descriptors — raise
``NotImplementedError`` from ``bind_tools``.

This module centralises the "bind tools, or fall back to a deterministic
pre-fetch" decision so all three analysts degrade the same way::

    bound = bind_tools_or_none(llm, tools, "Market Analyst")
    if bound is not None:
        ...                       # model-driven tool loop (key-based providers)
    else:
        ...                       # pre-fetch data, inject it into the prompt

This mirrors :func:`tradingagents.agents.utils.structured.bind_structured`,
which does the same ``NotImplementedError`` dance for
``with_structured_output`` so manager / trader / portfolio agents degrade
to free text on tool-less providers.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


def bind_tools_or_none(llm: Any, tools: List[Any], agent_name: str) -> Optional[Any]:
    """Return ``llm.bind_tools(tools)`` or ``None`` if the provider can't bind tools.

    Codex (and any other chat-only provider) raises ``NotImplementedError``
    from ``bind_tools`` because it drives its own tool-use loop. When that
    happens the caller falls back to a deterministic pre-fetch path that
    injects tool output straight into the prompt instead of letting the
    model call tools. A warning is logged so the operator understands the
    analyst is running tool-free for the rest of the run.
    """
    try:
        return llm.bind_tools(tools)
    except (NotImplementedError, AttributeError) as exc:
        logger.warning(
            "%s: provider does not support bind_tools (%s); falling back to "
            "deterministic data pre-fetch injected into the prompt",
            agent_name,
            exc,
        )
        return None


def safe_tool_text(label: str, fetch: Callable[[], Any]) -> str:
    """Run a single pre-fetch and always return a string, never raise.

    The tool-free analyst paths gather several independent data sources up
    front. One failing source (a flaky vendor, a missing fundamental) must
    not abort the whole analyst — it degrades to a clear ``<... unavailable>``
    placeholder so the model sees what is and isn't available, the same way
    the sentiment analyst's pre-fetchers degrade gracefully.
    """
    try:
        text = fetch()
    except Exception as exc:  # noqa: BLE001 — fail open, never block the analyst
        logger.warning("pre-fetch for %s failed: %s", label, exc)
        return f"<{label} unavailable: {exc}>"
    if text is None or not str(text).strip():
        return f"<{label} unavailable: empty result>"
    return str(text)
