"""Secretary analysis runners.

Default approved studies run one enriched TradingAgents graph. Committee mode
is explicit and opt-in.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, List, Optional

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.personas.loader import Persona, load_persona_from_file
from tradingagents.personas.resolver import personas_dir


log = logging.getLogger(__name__)


def _load_persona(persona_id: str) -> Persona:
    return load_persona_from_file(personas_dir() / f"{persona_id}.yaml")


def _overlay_for_persona(
    *,
    persona: Persona,
    config: dict,
    event_context: Optional[str],
    queue_job_id: Optional[int],
) -> dict:
    overlay = dict(config)
    overlay["persona_id"] = persona.id
    overlay["deep_think_llm"] = persona.llm.deep_think_llm
    overlay["quick_think_llm"] = persona.llm.quick_think_llm
    if persona.llm.deepseek_reasoning_effort is not None:
        overlay["deepseek_reasoning_effort"] = persona.llm.deepseek_reasoning_effort
    if persona.llm.openai_reasoning_effort is not None:
        overlay["openai_reasoning_effort"] = persona.llm.openai_reasoning_effort
    if persona.llm.anthropic_effort is not None:
        overlay["anthropic_effort"] = persona.llm.anthropic_effort
    if persona.llm.google_thinking_level is not None:
        overlay["google_thinking_level"] = persona.llm.google_thinking_level
    if event_context is not None:
        overlay["event_context"] = event_context
    if queue_job_id is not None:
        overlay["queue_job_id"] = queue_job_id
    if config.get("prior_analysis_pack"):
        overlay["prior_analysis_pack"] = config["prior_analysis_pack"]
    return overlay


def _run_one_graph(
    *,
    persona_id: str,
    ticker: str,
    trade_date: str,
    config: dict,
    event_context: Optional[str] = None,
    queue_job_id: Optional[int] = None,
) -> str:
    persona = _load_persona(persona_id)
    graph = TradingAgentsGraph(
        config=_overlay_for_persona(
            persona=persona,
            config=config,
            event_context=event_context,
            queue_job_id=queue_job_id,
        ),
        selected_analysts=list(persona.analysts.include),
    )
    graph.propagate(ticker, trade_date)
    return graph.run_id


def run_default_analysis(
    *,
    ticker: str,
    trade_date: str,
    config: dict,
    event_context: Optional[str] = None,
    queue_job_id: Optional[int] = None,
) -> List[str]:
    persona_id = config.get("default_analysis_persona_id", "balanced")
    return [
        _run_one_graph(
            persona_id=persona_id,
            ticker=ticker,
            trade_date=trade_date,
            config=config,
            event_context=event_context,
            queue_job_id=queue_job_id,
        )
    ]


def run_committee_analysis(
    *,
    persona_ids: Iterable[str],
    ticker: str,
    trade_date: str,
    config: dict,
    parallel: bool = True,
    event_context: Optional[str] = None,
    queue_job_id: Optional[int] = None,
) -> List[str]:
    ids = list(persona_ids)
    if not ids:
        raise RuntimeError("run_committee_analysis: empty persona list")

    def run_one(persona_id: str) -> str:
        return _run_one_graph(
            persona_id=persona_id,
            ticker=ticker,
            trade_date=trade_date,
            config=config,
            event_context=event_context,
            queue_job_id=queue_job_id,
        )

    if not parallel:
        return [run_one(persona_id) for persona_id in ids]

    run_ids: list[str] = []
    failures = 0
    with ThreadPoolExecutor(max_workers=len(ids)) as ex:
        future_to_persona = {
            ex.submit(run_one, persona_id): persona_id for persona_id in ids
        }
        for fut, persona_id in future_to_persona.items():
            try:
                run_ids.append(fut.result())
            except Exception:
                failures += 1
                log.exception(
                    "committee persona %s failed for %s on %s; continuing",
                    persona_id,
                    ticker,
                    trade_date,
                )
    if not run_ids:
        raise RuntimeError("run_committee_analysis: all committee runs failed")
    if failures:
        log.warning(
            "run_committee_analysis: %d/%d persona(s) failed for %s on %s",
            failures,
            len(ids),
            ticker,
            trade_date,
        )
    return run_ids
