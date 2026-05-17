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


_MODEL_NAME      = "gpt-4o-mini"
_TIMEOUT_SECONDS = 30
_MAX_INPUT_CHARS = 12_000


# Module-level ChatOpenAI singleton. The underlying httpx AsyncClient
# (which manages the TCP pool to api.openai.com) lives on the instance —
# recreating ChatOpenAI per call meant a fresh TLS handshake to OpenAI
# on every extraction. With 12 agents per run, that's 12 unnecessary
# handshakes. Lazy init so import-time isn't penalized when OPENAI_API_KEY
# isn't yet in env (e.g., during alembic-migration-only deploys).
_llm: ChatOpenAI | None = None


def _get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model       = _MODEL_NAME,
            temperature = 0,
            timeout     = _TIMEOUT_SECONDS,
            max_retries = 0,  # we handle retries at the cap level
        )
    return _llm


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
        structured = _get_llm().with_structured_output(schema_cls)
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
