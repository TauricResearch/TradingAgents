"""AgentSpec: an evidence agent is configuration, not a class.

Each roster entry declares who the agent is (persona), which slice of the
deterministic MarketSnapshot it may see (selectors), and at what timeframe
it reasons. The shared EvidenceAgent runtime does the rest, so 59 agents
are 59 of these records — not 59 classes (ADR-0014).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tradingagents.contracts import AgentTeam, Timeframe


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    team: AgentTeam
    persona: str
    timeframe: Timeframe = Timeframe.D1
    # --- snapshot selectors -------------------------------------------------
    indicators: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()  # names looked up in macro + onchain + extras
    include_bars: int = 0  # last-N bars table (pattern-reading agents)
    include_quote: bool = False
    include_session: bool = False
    include_news: int = 0  # last-N news items (news/sentiment agents)
    all_timeframes: bool = False  # multi-timeframe agents match any TF
    primary: tuple[str, ...] = ()  # if set, abstain unless >=1 of these rendered
    # --- runtime hints ------------------------------------------------------
    deep_think: bool = False
    notes: str = field(default="", compare=False)  # roster documentation only

    def __post_init__(self):
        if not self.agent_id or not self.agent_id.islower():
            raise ValueError(f"agent_id must be non-empty lowercase snake, got {self.agent_id!r}")
        selects_something = (
            self.indicators
            or self.metrics
            or self.include_bars
            or self.include_quote
            or self.include_news
        )
        if not selects_something:
            raise ValueError(
                f"{self.agent_id}: spec selects no data; an evidence agent with no "
                "inputs can never produce valid evidence"
            )
