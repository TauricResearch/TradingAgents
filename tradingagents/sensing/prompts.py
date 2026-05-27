"""Salience-LLM prompt construction.

The body matches §5 of the F3 design verbatim; only the substitutions
(watchlist, macro context, envelope fields) are dynamic.
"""

from __future__ import annotations

import json
from typing import Sequence

from .envelope import Envelope


_PROMPT_TEMPLATE = """You are scoring market-relevance for an investment watchlist.

ACTIVE WATCHLIST: {watchlist_csv}
RECENT MACRO CONTEXT (last 4h, may be empty): {macro_context}

EVENT SOURCE: {source}
EVENT TIMESTAMP: {ingested_ts}
EVENT TEXT (first 800 chars): {text}
SOURCE-PROVIDED TICKER TAGS (may be empty): {source_tags}

Return strictly JSON:
{{
  "salience": <float 0.0-1.0>,
  "matched_tickers": [<ticker from watchlist that this materially involves>],
  "mentioned_tickers": [{{"ticker": "<symbol>", "confidence": <float 0-1>}}],
  "reason": "<one sentence>"
}}

Salience anchors:
  0.0-0.3 : routine, no clear watchlist relevance
  0.3-0.6 : context relevant but unlikely to move prices alone
  0.6-0.85: directly relevant to a watchlist instrument
  0.85-1.0: high-impact, time-sensitive, watchlist-relevant
"""


def build_salience_prompt(
    *,
    env: Envelope,
    watchlist: Sequence[str],
    macro_context: str,
) -> str:
    return _PROMPT_TEMPLATE.format(
        watchlist_csv=", ".join(watchlist) if watchlist else "(none)",
        macro_context=macro_context or "(none)",
        source=env.source,
        ingested_ts=env.ingested_ts,
        text=env.text[:800],
        source_tags=json.dumps(env.source_tags),
    )
