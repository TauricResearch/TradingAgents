"""Salience-LLM prompt construction.

The body matches §5 of the F3 design verbatim; only the substitutions
(watchlist, macro context, envelope fields) are dynamic.

Cache layout
------------
DeepSeek's automatic prompt cache reuses only the longest BYTE-IDENTICAL
prefix from the start of the input. This per-event call fires thousands of
times a day, so the prompt is split into:

  1. ``_PROMPT_PREFIX`` — the stable instructions + the full "Return strictly
     JSON {...}" schema + the salience anchors. Byte-identical on every call,
     so the whole block is a cache hit.
  2. a VARIABLE tail appended after the prefix, ordered least-volatile-first
     (watchlist, then macro context, then the per-event envelope fields).

The output contract (single string, same JSON keys, same anchors) is
unchanged — only the ORDER of the sections moved.
"""

from __future__ import annotations

import json
from typing import Sequence

from .envelope import Envelope


# 1. STABLE PREFIX — no interpolation, byte-identical across every event.
_PROMPT_PREFIX = """You are scoring market-relevance for an investment watchlist.

Return strictly JSON:
{
  "salience": <float 0.0-1.0>,
  "matched_tickers": [<ticker from watchlist that this materially involves>],
  "mentioned_tickers": [{"ticker": "<symbol>", "confidence": <float 0-1>}],
  "reason": "<one sentence>"
}

Salience anchors:
  0.0-0.3 : routine, no clear watchlist relevance
  0.3-0.6 : context relevant but unlikely to move prices alone
  0.6-0.85: directly relevant to a watchlist instrument
  0.85-1.0: high-impact, time-sensitive, watchlist-relevant

The active watchlist, recent macro context, and the event to score follow.
"""


# 2. VARIABLE TAIL — least-volatile-first (watchlist, macro, then per-event).
_PROMPT_TAIL = """
ACTIVE WATCHLIST: {watchlist_csv}
RECENT MACRO CONTEXT (last 4h, may be empty): {macro_context}

EVENT SOURCE: {source}
EVENT TIMESTAMP: {ingested_ts}
EVENT TEXT (first 800 chars): {text}
SOURCE-PROVIDED TICKER TAGS (may be empty): {source_tags}
"""


def build_salience_prompt(
    *,
    env: Envelope,
    watchlist: Sequence[str],
    macro_context: str,
) -> str:
    # Stable prefix FIRST (byte-identical -> cache hit), variable tail LAST.
    return _PROMPT_PREFIX + _PROMPT_TAIL.format(
        watchlist_csv=", ".join(watchlist) if watchlist else "(none)",
        macro_context=macro_context or "(none)",
        source=env.source,
        ingested_ts=env.ingested_ts,
        text=env.text[:800],
        source_tags=json.dumps(env.source_tags),
    )
