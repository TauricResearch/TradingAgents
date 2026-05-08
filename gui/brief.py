"""Plain-English "what should I actually do" brief for a completed run.

The framework's analyst reports and the Portfolio Manager's final
decision are detailed but technical. A novice reading them has to dig
through prose to find the actionable bits: decision, position size,
timeframe, entry/exit triggers, key risks.

This module asks the user's *quick-think* model to extract those into
a structured ``Brief`` (Pydantic schema, validated by LangChain's
``.with_structured_output``). The generated brief is cached per run
in SQLite so re-opening a run is instant — no LLM call.

Why quick-think and not deep-think:
- Extraction over already-written text is exactly the job model tiers
  like Haiku / gpt-4o-mini are good at.
- It's cheap (typically <$0.005 per brief) so users can run it
  routinely on every analysis.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from gui import storage
from gui.chat import _build_llm, bootstrap_env


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class Trigger(BaseModel):
    """A specific market/data condition that should drive an action."""
    condition: str = Field(
        description=(
            "Specific, measurable market or data condition. Be concrete "
            "with numbers and timeframe where possible. "
            "Example: 'NVDA closes below $183 (200-day SMA)' or "
            "'Q3 revenue miss > 5% vs consensus'."
        )
    )
    action: str = Field(
        description=(
            "Concrete action to take when the condition fires. "
            "Example: 'Reduce position by 50%; reassess thesis' or "
            "'Add tranche 2 (~45% of target weight)'."
        )
    )


class Brief(BaseModel):
    """Plain-English summary a non-expert can act on."""

    decision: str = Field(
        description="The single-word verdict: BUY, SELL, HOLD, REDUCE, AVOID, or WATCH."
    )
    tldr: str = Field(
        description=(
            "2-3 sentence plain-English summary a non-investor would understand. "
            "Avoid jargon. Lead with what action to take."
        )
    )
    timeframe: str = Field(
        description=(
            "How long this view is expected to hold, e.g. '4-6 weeks', "
            "'3-6 months', 'long-term core position'. If the analysis "
            "doesn't say, infer the most likely horizon based on the reasoning."
        )
    )
    position_size: str = Field(
        description=(
            "Recommended portfolio weight or sizing guidance. "
            "Example: '4-5% of portfolio in three tranches' or 'starter position only'."
        )
    )
    entry_strategy: str = Field(
        description=(
            "How to enter — lump sum vs scaled, with price targets where the "
            "analysis provides them. One or two short sentences."
        )
    )
    stop_loss: str = Field(
        description=(
            "Conditions or price level at which to exit if the thesis is wrong. "
            "Quote the analysis's specific level if given."
        )
    )
    take_profit: str = Field(
        description=(
            "Conditions or price level at which to take profits / scale out. "
            "May be 'no explicit target — review at <date/condition>'."
        )
    )
    triggers: List[Trigger] = Field(
        description=(
            "3-7 specific if-then trigger points the user should watch for. "
            "These are the 'tripwires' that should drive action."
        )
    )
    key_risks: List[str] = Field(
        description=(
            "3-5 main risks to this thesis, written in plain English. "
            "What would make this trade fail?"
        )
    )
    benchmark_view: str = Field(
        description=(
            "One sentence on whether this is expected to outperform a "
            "passive S&P 500 (SPY) hold over the recommended timeframe, "
            "and roughly by how much / why. Be honest if the answer is 'unclear'."
        )
    )

    def to_markdown(self) -> str:
        triggers_md = "\n".join(
            f"- **If** {t.condition.strip()} → {t.action.strip()}"
            for t in self.triggers
        ) or "_(none extracted)_"
        risks_md = "\n".join(f"- {r.strip()}" for r in self.key_risks) or "_(none)_"
        return (
            f"### {self.decision}\n\n"
            f"{self.tldr.strip()}\n\n"
            f"**Timeframe:** {self.timeframe.strip()}  \n"
            f"**Position size:** {self.position_size.strip()}  \n"
            f"**Entry:** {self.entry_strategy.strip()}  \n"
            f"**Stop loss:** {self.stop_loss.strip()}  \n"
            f"**Take profit:** {self.take_profit.strip()}\n\n"
            f"#### Trigger points\n\n{triggers_md}\n\n"
            f"#### Key risks\n\n{risks_md}\n\n"
            f"**vs S&P 500:** {self.benchmark_view.strip()}\n"
        )


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

_PROMPT_HEADER = (
    "You are extracting an actionable trading brief from a multi-agent "
    "stock analysis. The analysis covers fundamentals, sentiment, news, "
    "technical indicators, a bull/bear debate, a trader plan, and a "
    "risk-management debate, ending with a final Portfolio Manager "
    "decision.\n\n"
    "Your job: read the full analysis below and produce a structured brief "
    "a non-expert investor can act on. Quote specific prices, levels, and "
    "timeframes from the analysis whenever it gives them. If the analysis "
    "is silent on a field, give the most reasonable inference based on the "
    "rest of the content (don't say 'not specified' — make the call). Keep "
    "all language plain and free of jargon.\n"
)


def _state_text_for_brief(state: Dict[str, Any]) -> str:
    """Compact textual rendering of the run state for the brief prompt."""
    pieces: List[str] = []

    def add(label: str, body: Optional[str]) -> None:
        if body:
            pieces.append(f"## {label}\n\n{body}\n")

    add("Market", state.get("market_report"))
    add("Sentiment", state.get("sentiment_report"))
    add("News", state.get("news_report"))
    add("Fundamentals", state.get("fundamentals_report"))

    debate = state.get("investment_debate_state") or {}
    add("Bull case", debate.get("bull_history"))
    add("Bear case", debate.get("bear_history"))
    add("Research manager verdict", debate.get("judge_decision"))

    add("Trader plan",
        state.get("trader_investment_decision")
        or state.get("trader_investment_plan")
        or state.get("investment_plan"))

    risk = state.get("risk_debate_state") or {}
    add("Aggressive risk view", risk.get("aggressive_history"))
    add("Conservative risk view", risk.get("conservative_history"))
    add("Neutral risk view", risk.get("neutral_history"))
    add("Risk judge", risk.get("judge_decision"))
    add("FINAL PM DECISION", state.get("final_trade_decision"))

    return "\n".join(pieces)


def generate_brief(state: Dict[str, Any], meta: Dict[str, Any]) -> Brief:
    """Run the LLM call to produce a structured brief.

    Doesn't touch any cache. Callers should normally use ``get_brief``.
    """
    bootstrap_env()
    llm = _build_llm()
    structured = llm.with_structured_output(Brief)

    user_prompt = (
        f"Ticker: {meta.get('ticker', '?')}\n"
        f"Trade date: {meta.get('trade_date', '?')}\n"
        f"Final decision (one-word): {meta.get('decision') or '—'}\n\n"
        + _state_text_for_brief(state)
    )

    return structured.invoke(_PROMPT_HEADER + "\n\n" + user_prompt)


# ---------------------------------------------------------------------------
# Cache (SQLite)
# ---------------------------------------------------------------------------

_BRIEF_COLUMN_INITIALIZED = False


def _ensure_column() -> None:
    """Lazy-add the ``brief_json`` column on first use.

    Old DBs created before this feature don't have the column; rather
    than ship a migration system for what is currently a single table
    addition, we ALTER on demand. The ``OperationalError`` on duplicate
    add is swallowed so repeated calls are no-ops.
    """
    global _BRIEF_COLUMN_INITIALIZED
    if _BRIEF_COLUMN_INITIALIZED:
        return
    storage.init_db()
    try:
        with sqlite3.connect(storage.DB_PATH) as c:
            c.execute("ALTER TABLE runs ADD COLUMN brief_json TEXT")
            c.commit()
    except sqlite3.OperationalError:
        # Column already exists.
        pass
    _BRIEF_COLUMN_INITIALIZED = True


def get_cached_brief(run_id: str) -> Optional[Brief]:
    """Return the cached brief for a run, or ``None`` if none generated yet."""
    if not run_id:
        return None
    _ensure_column()
    with sqlite3.connect(storage.DB_PATH) as c:
        c.row_factory = sqlite3.Row
        row = c.execute("SELECT brief_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not row or not row["brief_json"]:
        return None
    try:
        return Brief.model_validate_json(row["brief_json"])
    except Exception:
        return None


def store_brief(run_id: str, brief: Brief) -> None:
    if not run_id:
        return
    _ensure_column()
    with sqlite3.connect(storage.DB_PATH) as c:
        c.execute(
            "UPDATE runs SET brief_json=? WHERE run_id=?",
            (brief.model_dump_json(), run_id),
        )
        c.commit()


def get_or_generate_brief(run_id: str, state: Dict[str, Any],
                          meta: Dict[str, Any]) -> Brief:
    """Return the cached brief or generate one (and cache it)."""
    cached = get_cached_brief(run_id)
    if cached is not None:
        return cached
    brief = generate_brief(state, meta)
    store_brief(run_id, brief)
    return brief
