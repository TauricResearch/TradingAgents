"""
LangChain callback handler that bridges per-agent output to:
  1. The `agent_reports` Postgres table (durable record for replay/UI)
  2. The `run:<run_id>` Redis pub-sub channel (live SSE stream)

Wired into the LangGraph stream via the `callbacks` config option in
`trading_agents_runner.run_analysis`. Each chain end-event corresponds
roughly to one agent's output (the TradingAgents pipeline structures
each agent as its own LangChain chain).

Treat the BASE (RunRecorderHandler) as a python-temp-pro template — the
shape works for any LangGraph chain. The trading-specific
interpretation (mapping chain names to agent_reports rows) is the only
app-specific code here.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from langchain_core.callbacks.base import AsyncCallbackHandler
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import AgentReport
from app.services.extractors import extract_metadata
from app.services.pubsub import publish_event


logger = logging.getLogger(__name__)


# TT-295: previously this only looked at `serialized.name`, which under
# LangGraph returns generic strings like "RunnableSequence" and lost the
# real agent identity. The dashboard's agent_reports list rendered every
# row as "unknown" because of this.
#
# Lookup priority:
#   1. metadata.langgraph_node  — LangGraph sets this for each node call.
#                                 Most accurate for TradingAgents since
#                                 it constructs the pipeline as a graph.
#   2. name kwarg               — LangChain passes the explicit name when
#                                 a chain was constructed with one.
#   3. serialized.name / .id    — legacy fallback for non-LangGraph chains.
#   4. "unknown"                — last resort.
_GENERIC_NAMES = {"RunnableSequence", "Runnable", "Chain", "Agent"}


def _normalize_agent_name(
    serialized: dict[str, Any] | None,
    metadata:   dict[str, Any] | None = None,
    name_kw:    str | None            = None,
) -> str:
    # 1. LangGraph metadata.
    if metadata:
        node = metadata.get("langgraph_node")
        if node:
            return str(node)

    # 2. Explicit name kwarg.
    if name_kw:
        cleaned = _strip_suffixes(str(name_kw))
        if cleaned and cleaned not in _GENERIC_NAMES:
            return cleaned

    # 3. serialized.name / serialized.id legacy.
    if serialized:
        name = serialized.get("name") or serialized.get("id", [""])[-1]
        if name:
            cleaned = _strip_suffixes(str(name))
            if cleaned and cleaned not in _GENERIC_NAMES:
                return cleaned

    return "unknown"


def _strip_suffixes(name: str) -> str:
    """Drop a single trailing 'Chain' / 'Agent' / 'Runnable' suffix if present."""
    for suffix in ("Chain", "Agent", "Runnable"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


class RunRecorderHandler(AsyncCallbackHandler):
    """
    Captures each agent's output as the TradingAgents graph runs. One
    instance per analysis run — owns the run_id for tagging.

    Tradeoff note: we capture on `on_chain_end` rather than per LLM call.
    A single agent typically makes multiple LLM calls (one for thinking,
    one for response, etc.); capturing per-LLM would flood agent_reports
    with intermediate steps. Per-chain gives one row per agent's full
    output cycle, which matches the user's mental model of "this agent
    finished its analysis."
    """

    # AsyncCallbackHandler requires this flag for it to be invoked in
    # async runs.
    run_inline = False

    def __init__(
        self,
        run_id: str,
        sessionmaker: async_sessionmaker,
    ):
        super().__init__()
        self._run_id = run_id
        self._sessionmaker = sessionmaker
        # Track chain run UUIDs so we can correlate start/end pairs and
        # know what agent each chain belongs to.
        self._active: dict[UUID, str] = {}

    async def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        # TT-295: pull langgraph_node from metadata + explicit name kwarg.
        agent_name = _normalize_agent_name(
            serialized,
            metadata=kwargs.get("metadata"),
            name_kw=kwargs.get("name"),
        )
        self._active[run_id] = agent_name
        # Live event: agent started. Browser uses this to show a "thinking..."
        # row in the UI immediately, before any output exists.
        await publish_event(
            self._run_id,
            {
                "type": "agent_started",
                "agent": agent_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        agent_name = self._active.pop(run_id, "unknown")
        # Stringify the chain output for storage. LangChain outputs are
        # dicts of varying shape — JSON.dumps preserves structure when
        # consumers want to parse, but the agent_reports.content column
        # is plain Text since most consumers will render directly.
        content = _outputs_to_text(outputs)

        # TT-295: best-effort structured-data extraction. Failure (LLM
        # timeout, validation error, no schema for agent) nulls the
        # metadata field but never blocks the agent_reports row write.
        metadata = await extract_metadata(agent_name, content)

        # Persist durably.
        async with self._sessionmaker() as session:
            try:
                session.add(
                    AgentReport(
                        run_id=self._run_id,
                        agent_name=agent_name,
                        content=content,
                        # Python attr is `report_metadata`; DB column is
                        # still "metadata". See models.py for the why.
                        report_metadata=metadata,
                    )
                )
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.warning(
                    "AgentReport persist failed for run %s agent %s: %s",
                    self._run_id, agent_name, e,
                )

        # Live event: agent finished, here's its output. Browser appends
        # this to the scrolling agent-output panel.
        await publish_event(
            self._run_id,
            {
                "type": "agent_finished",
                "agent": agent_name,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        agent_name = self._active.pop(run_id, "unknown")
        logger.error("Chain error in agent %s: %s", agent_name, error)
        await publish_event(
            self._run_id,
            {
                "type": "agent_error",
                "agent": agent_name,
                "error": str(error),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


def _outputs_to_text(outputs: dict[str, Any]) -> str:
    """
    Best-effort string serialization of a chain's output dict. Common
    shapes:
      - {"output": "..."}             → just the output
      - {"messages": [Message(...)]}  → last message content
      - {"final_trade_decision": "..."} → that string
      - everything else                → str(dict)
    """
    if not outputs:
        return ""
    if "output" in outputs and isinstance(outputs["output"], str):
        return outputs["output"]
    if "messages" in outputs and outputs["messages"]:
        last = outputs["messages"][-1]
        content = getattr(last, "content", None)
        if content:
            return str(content)
    # TradingAgents-specific terminal state key — included since it's the
    # one place the upstream library names its final output.
    if "final_trade_decision" in outputs and outputs["final_trade_decision"]:
        return str(outputs["final_trade_decision"])
    return str(outputs)
