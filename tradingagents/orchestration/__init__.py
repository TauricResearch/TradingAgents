"""Orchestration: the cycle runner that ties the whole alpha together.

Flow (the funnel + trigger engine of the wiki):

    Trigger Engine  ->  priority queue  ->  analyze (LLM graph)  ->  cost gate  ->  execute

The ``analyze`` step is a pluggable hook: Luca's LangGraph implements the
``Analyzer`` signature; until then a ``hold_analyzer`` stub keeps the runner
fully testable without any LLM.
"""

from .triggers import TriggerEvent, collect_triggers
from .analyze import Analyzer, hold_analyzer
from .cycle import CycleReport, run_cycle

__all__ = [
    "TriggerEvent",
    "collect_triggers",
    "Analyzer",
    "hold_analyzer",
    "CycleReport",
    "run_cycle",
]
