"""Director level — fan-out per-ticker evaluators + portfolio decision.

Three-level hierarchy (wiki):
  Director (one) -> Evaluators (one per ticker, in parallel) -> 4 desks
The Evaluator is the existing per-ticker brain graph (``analyze_symbol``); the
Director fans those out in parallel (bounded), collects the theses, then applies
the portfolio-level Statute (the aggregate the single ticker can't see).

Parallelism: a bounded thread pool gives real concurrency for the blocking LLM
calls; each worker uses its own DB session. With SQLite + free rate-limited
models the effective concurrency is modest (keep ``max_parallel`` small);
Postgres + paid models scale it.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from ..domain.state import ResearchState
from .graph import analyze_symbol
from .llm import StructuredLLM
from .tooling import Extractors


def analyze_batch(
    symbols: list[str],
    llm: StructuredLLM,
    *,
    session_factory: Callable[[], Any],
    max_parallel: int = 3,
    max_revisions: int = 1,
    charter: Optional[dict[str, Any]] = None,
    base_risk_pct: float = 0.01,
    extractors: Optional[Extractors] = None,
) -> dict[str, ResearchState]:
    """Run a per-ticker Evaluator for each symbol, in parallel. Returns theses.

    ``session_factory()`` must yield a context-manager session (like
    ``database.get_session()``); each evaluator gets its own.
    """
    if not symbols:
        return {}

    def _one(symbol: str) -> tuple[str, Optional[ResearchState]]:
        try:
            with session_factory() as s:
                state = analyze_symbol(
                    s, symbol, llm, max_revisions=max_revisions,
                    charter=charter, base_risk_pct=base_risk_pct, extractors=extractors,
                )
            return symbol, state
        except Exception:
            return symbol, None

    results: dict[str, ResearchState] = {}
    workers = max(1, min(max_parallel, len(symbols)))
    if workers == 1:
        for sym in symbols:
            _, st = _one(sym)
            if st is not None:
                results[sym] = st
        return results

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for sym, st in pool.map(_one, symbols):
            if st is not None:
                results[sym] = st
    return results
