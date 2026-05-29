"""Shared persona-fan-out helper.

Both ``cli.deepdive.run_deepdive`` and
``Secretary.compose_event_alert`` use this to launch N persona-overlaid
TradingAgentsGraph runs in parallel and collect their run_ids.

Lifted out of cli/deepdive.py so the worker path doesn't need a CLI
dependency to run personas.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from tradingagents.personas.loader import Persona


log = logging.getLogger(__name__)


def _run_one_persona(
    persona: Persona,
    ticker: str,
    trade_date: str,
    config: dict,
    event_context: Optional[str] = None,
    queue_job_id: Optional[int] = None,
) -> str:
    """Construct a TradingAgentsGraph with the persona overlay, propagate,
    return the run_id.

    ``event_context`` is threaded into the per-run config as ``event_context``;
    the graph reads it from config and injects it into the initial state
    (see Task 11).

    ``queue_job_id`` is threaded into the per-run config as ``queue_job_id``;
    the graph's RunRecorder writes it into the ``runs.queue_job_id`` column
    (see Task 9).
    """
    overlay = dict(config)
    overlay["persona_id"] = persona.id
    overlay["deep_think_llm"] = persona.llm.deep_think_llm
    overlay["quick_think_llm"] = persona.llm.quick_think_llm
    if persona.llm.deepseek_reasoning_effort is not None:
        overlay["deepseek_reasoning_effort"] = persona.llm.deepseek_reasoning_effort
    if event_context is not None:
        overlay["event_context"] = event_context
    if queue_job_id is not None:
        overlay["queue_job_id"] = queue_job_id

    selected = list(persona.analysts.include)

    # Import here to keep this module light when only the helper is needed.
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph(config=overlay, selected_analysts=selected)
    graph.propagate(ticker, trade_date)
    return graph.run_id


def run_personas_parallel(
    *,
    personas: List[Persona],
    ticker: str,
    trade_date: str,
    config: dict,
    parallel: bool = True,
    event_context: Optional[str] = None,
    queue_job_id: Optional[int] = None,
) -> List[str]:
    """Run each persona, return the run_ids of the SURVIVING runs.

    With ``parallel=True`` (default), uses a ThreadPoolExecutor sized to the
    persona count. With ``parallel=False``, runs sequentially (used by tests
    and for deterministic debugging).

    Error isolation (S-3): a single persona raising (e.g. a transient LLM
    error) must not discard the whole brief. We collect every successful
    PersonaRun's run_id and log each failure. We only raise — failing the
    whole job — when ZERO personas succeed (quorum of >=1, which is what the
    downstream brief synthesis needs to produce anything). The non-parallel
    branch isolates per-persona identically so behavior stays consistent.
    """
    if not personas:
        raise RuntimeError("run_personas_parallel: empty personas list")

    run_ids: List[str] = []
    failures = 0

    if parallel:
        with ThreadPoolExecutor(max_workers=len(personas)) as ex:
            # Map each future back to its persona so failure logs are useful.
            future_to_persona = {
                ex.submit(
                    _run_one_persona, p, ticker, trade_date, config,
                    event_context, queue_job_id,
                ): p
                for p in personas
            }
            for fut, persona in future_to_persona.items():
                try:
                    run_ids.append(fut.result())
                except Exception:
                    failures += 1
                    log.exception(
                        "persona %s failed for %s on %s; "
                        "isolating and continuing",
                        persona.id, ticker, trade_date,
                    )
    else:
        for persona in personas:
            try:
                run_ids.append(
                    _run_one_persona(
                        persona, ticker, trade_date, config,
                        event_context, queue_job_id,
                    )
                )
            except Exception:
                failures += 1
                log.exception(
                    "persona %s failed for %s on %s; "
                    "isolating and continuing",
                    persona.id, ticker, trade_date,
                )

    if not run_ids:
        # Quorum not met: every persona failed, so there is nothing to
        # synthesize a brief from. Surface this so the job is marked error.
        raise RuntimeError(
            f"run_personas_parallel: all {len(personas)} persona(s) failed "
            f"for {ticker} on {trade_date}; no surviving runs"
        )

    if failures:
        log.warning(
            "run_personas_parallel: %d/%d persona(s) failed for %s on %s; "
            "proceeding with %d surviving run(s)",
            failures, len(personas), ticker, trade_date, len(run_ids),
        )

    return run_ids
