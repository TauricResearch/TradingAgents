"""The analyze hook: where the LLM graph plugs in.

``Analyzer`` is the contract: given a session and a symbol, produce a (possibly
approved) ResearchState — or None to skip. Luca's LangGraph implements this.
``hold_analyzer`` is a no-LLM stub that returns a complete HOLD thesis, so the
cycle runner is fully testable today.
"""

from __future__ import annotations

from typing import Optional, Protocol

from sqlalchemy.orm import Session

from ..domain.enums import Direction, RiskVerdict
from ..domain.state import ResearchState


class Analyzer(Protocol):
    def __call__(self, session: Session, symbol: str) -> Optional[ResearchState]: ...


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
