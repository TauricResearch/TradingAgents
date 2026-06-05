"""The analyze hook: the brain plugs in here.

``Analyzer`` is the contract: given a session and a symbol, produce a (possibly
approved) ResearchState — or None to skip. ``make_brain_analyzer`` wires the
real brain graph; ``hold_analyzer`` is a no-LLM stub so the cycle runner is
testable without any model.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from sqlalchemy.orm import Session

from ..domain.enums import Direction, RiskVerdict
from ..domain.state import ResearchState


class Analyzer(Protocol):
    def __call__(self, session: Session, symbol: str) -> Optional[ResearchState]: ...


def make_brain_analyzer(llm: Any, **brain_kwargs: Any) -> Analyzer:
    """Build an Analyzer backed by the brain graph (our wiki topology)."""
    from ..brain import analyze_symbol

    def analyzer(session: Session, symbol: str) -> ResearchState:
        return analyze_symbol(session, symbol, llm, **brain_kwargs)

    return analyzer


def hold_analyzer(session: Session, symbol: str) -> ResearchState:
    """Stub analyzer: a complete, approved HOLD thesis (nothing to execute)."""
    state = ResearchState(
        ticker=symbol,
        market_view="(stub)", sentiment_view="(stub)",
        fundamental_view="(stub)", technical_view="(stub)",
        direction=Direction.HOLD, conviction_level=Direction.HOLD,
    )
    state.risk.verdict = RiskVerdict.APPROVED
    return state
