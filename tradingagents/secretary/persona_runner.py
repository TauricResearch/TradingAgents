"""Shared persona-fan-out helper.

Both ``cli.deepdive.run_deepdive`` and
``Secretary.compose_event_alert`` use this to launch N persona-overlaid
TradingAgentsGraph runs in parallel and collect their run_ids.

Lifted out of cli/deepdive.py so the worker path doesn't need a CLI
dependency to run personas.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from tradingagents.personas.loader import Persona


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
    """Run each persona, return run_ids in completion order.

    With ``parallel=True`` (default), uses a ThreadPoolExecutor sized to the
    persona count. With ``parallel=False``, runs sequentially (used by tests
    and for deterministic debugging).
    """
    if not personas:
        raise RuntimeError("run_personas_parallel: empty personas list")

    if parallel:
        with ThreadPoolExecutor(max_workers=len(personas)) as ex:
            futures = [
                ex.submit(
                    _run_one_persona, p, ticker, trade_date, config,
                    event_context, queue_job_id,
                )
                for p in personas
            ]
            return [f.result() for f in futures]
    return [
        _run_one_persona(
            p, ticker, trade_date, config, event_context, queue_job_id,
        )
        for p in personas
    ]
