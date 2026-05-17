"""
TT-295: extract structured metadata from an agent's markdown report.

Single function `extract_metadata(agent_name, content)`. Looks up the
agent's schema in `schemas.SCHEMA_FOR_AGENT`, runs a gpt-4o-mini call
with LangChain's `with_structured_output`, returns the dict on success
or None on any failure.

Best-effort policy (TT-295 design call): if extraction fails for any
reason — no schema for this agent, LLM timeout, malformed response,
network error — return None. The caller writes a normal agent_reports
row with `metadata = null`. The agent's prose content is never lost,
the structured side-channel just doesn't get populated this time.

Model choice: gpt-4o-mini. Roughly $0.15 / 1M input tokens, $0.60 /
1M output. At ~3k input tokens (an analyst report) and ~200 output
tokens (a small JSON dict), each extraction costs ~$0.0006. Twelve
agents per run × $0.0006 = under a cent per run; negligible vs the
main TradingAgents loop.

Cap input at 12k chars: a useful guardrail against runaway analyst
output that would balloon cost. The first chunk of any analyst report
holds the quantitative facts; later paragraphs are usually elaboration.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from .schemas import SCHEMA_FOR_AGENT


logger = logging.getLogger(__name__)


# Aggressive timeout (was 30s) — gpt-4o-mini structured-output usually
# resolves in 1-3s. A 30s budget meant a failing extractor blocked the
# LangChain callback for that whole window per agent, cascading into
# chain errors and retry loops. 8s gives us 2x normal latency headroom
# while ensuring the run keeps moving when OpenAI is sluggish.
_MODEL_NAME      = "gpt-4o-mini"
_TIMEOUT_SECONDS = 8
_MAX_INPUT_CHARS = 12_000


async def extract_metadata(agent_name: str, content: str) -> Optional[dict[str, Any]]:
    """
    Extract structured metadata for one agent_report. Returns a JSON-
    serializable dict on success, None on any failure.
    """
    schema_cls = SCHEMA_FOR_AGENT.get(agent_name)
    if not schema_cls:
        # Agent doesn't have a schema yet — nothing to extract.
        return None
    if not content:
        return None

    truncated = content[:_MAX_INPUT_CHARS]

    prompt = (
        f"You are a precise data extractor for financial analyst reports. "
        f"The following text is the output of a `{agent_name}` agent in a "
        f"multi-agent equity-research pipeline. Extract the requested "
        f"fields per the JSON schema. Critical rules:\n"
        f"  • Use null for any field the report does not explicitly state.\n"
        f"  • Do NOT infer or estimate numbers the analyst didn't cite.\n"
        f"  • For enum fields, pick the closest match or null.\n\n"
        f"Report:\n```\n{truncated}\n```\n"
    )

    try:
        # Per-call instantiation: a module-level singleton ChatOpenAI
        # was tried but the underlying httpx AsyncClient gets bound to
        # the event loop at construction time, and LangGraph dispatches
        # callbacks across loops — singleton crossed loops and failed
        # with "got Future attached to a different loop". Per-call
        # overhead is minor and uniform; correctness wins.
        llm = ChatOpenAI(
            model       = _MODEL_NAME,
            temperature = 0,
            timeout     = _TIMEOUT_SECONDS,
            max_retries = 0,
        )
        structured = llm.with_structured_output(schema_cls)
        result = await asyncio.wait_for(
            structured.ainvoke(prompt),
            timeout=_TIMEOUT_SECONDS,
        )
        # Pydantic v2: model_dump(mode="json") yields JSON-safe types.
        return result.model_dump(mode="json")  # type: ignore[union-attr]
    except asyncio.TimeoutError:
        logger.warning("Extractor timed out for agent %s", agent_name)
        return None
    except Exception as e:
        # Anything else — schema validation, LLM error, network — logged
        # and swallowed. The agent's prose content is the priority.
        logger.warning("Extractor failed for agent %s: %s", agent_name, e)
        return None
