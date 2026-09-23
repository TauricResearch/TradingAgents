"""TypeSafe Jev access for agents that ask typed questions.

Jev (https://docs.typesafe.ai) answers questions about natural-language state
with typed values: the probability of a yes (Noul), a distribution over named
options (Choice), or a position on described levels (Score). Agents use it for
cheap judgments around their LLM calls; the LLMs keep writing the reports, and
arithmetic, dates and counting stay in code.

Jev is optional. ``jev_client`` returns None when the ``jev`` extra is not
installed, ``TYPESAFE_API_KEY`` is unset, or ``jev_enabled`` is off in the
config, and every caller then behaves as it did without Jev.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from tradingagents.dataflows.config import get_config

logger = logging.getLogger(__name__)

# Requests in flight at once. The service allows 1,200 requests a minute and the
# SDK retries a 429 with backoff, so this bounds latency, not correctness.
MAX_CONCURRENT_REQUESTS = 8


def jev_client() -> Any | None:
    """A ``TypeSafeClient`` for the configured model, or None when Jev is off.

    Use the client as a context manager so its HTTP connections are closed.
    """
    config = get_config()
    if not config.get("jev_enabled", True):
        return None
    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        return None
    try:
        from typesafe_sdk import TypeSafeClient, TypeSafeError
    except ImportError:
        logger.warning(
            "TYPESAFE_API_KEY is set but typesafe-sdk is not installed; running without "
            'Jev. Install it with: pip install "tradingagents[jev]"'
        )
        return None
    try:
        return TypeSafeClient(model=config.get("jev_model") or None)
    except TypeSafeError as exc:  # a malformed key or timeout, caught before any request
        logger.warning("Could not create the TypeSafe client (%s); running without Jev", exc)
        return None


def ask_each(client: Any, states: Sequence[Any], questions: Mapping[str, Any]) -> list[Any]:
    """Ask the same ``questions`` about every state, one request per state.

    Requests run concurrently; responses come back in state order. The first
    request that still fails after the SDK's retries raises, so a caller never
    mixes judged and unjudged items without knowing.
    """
    if not states:
        return []
    workers = min(MAX_CONCURRENT_REQUESTS, len(states))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda state: client.system_one(state=state, questions=questions), states))
