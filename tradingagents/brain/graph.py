"""The brain: our wiki topology as a LangGraph.

State  = the project ResearchState (carried in the graph state).
Nodes  = our agents: Market, Sentiment, Technical, Fundamentals (the 2 desks),
         Portfolio Manager (aggregates), Risk Analyst (single bear gate).
Edges  = START -> 4 desks -> PM -> Risk -> (send_back/need_more_info loop, capped)
         -> END.

No bull/bear, no 3-way risk debate, no LLM trader (the trade is deterministic and
lives in ``execution``). Everything here matches ``system/agents.md`` +
``system/agent-behaviors.md`` + ``system/system-prompts.md``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from ..domain.enums import Direction, RiskVerdict
from ..domain.risk import atr_levels, check_guardrails, conviction_multiplier, position_size
from ..domain.state import AgentOpinion, ResearchState
from ..execution import inject_portfolio_state
from ..indicators import atr_from_db, indicator_snapshot
from ..tools import get_open_positions_risk, get_realtime_quote
from . import context, prompts
from .llm import StructuredLLM
from .schemas import DeskOpinion, PMDecision, RiskDecision
from .tooling import Extractors, build_desk_tools


class BrainState(TypedDict):
    symbol: str
    research_state: ResearchState
    revisions: int
    need_more_info: bool


def _set_opinion(rs: ResearchState, agent: str, op: DeskOpinion) -> None:
    rs.agent_opinions = [o for o in rs.agent_opinions if o.agent != agent]
    rs.agent_opinions.append(
        AgentOpinion(
            agent=agent,
            suggested_direction=op.suggested_direction,
            suggested_conviction=op.suggested_conviction,
            rationale=op.rationale,
        )
    )


def build_brain_graph(
    session: Session,
    llm: StructuredLLM,
    *,
    max_revisions: int = 1,
    charter: Optional[dict[str, Any]] = None,
    base_risk_pct: float = 0.01,
    extractors: Optional[Extractors] = None,
):
    """Compile the brain graph. Nodes close over session/llm/config.

    ``extractors`` carries the live fetchers + quote_fn behind the per-agent
    tools (the Extractors set); the desk agents call those tools autonomously.
    """
    if charter is None:
        from ..storage import repository as repo
        charter = repo.load_charter(session) or None
    quote_fn = extractors.quote_fn if extractors else None

    # --- desk nodes (each agent calls its own tools autonomously) -------
    def _desk(agent: str, prompt: str, ctx_fn):
        def node(state: BrainState) -> dict[str, Any]:
            rs = state["research_state"]
            tools = build_desk_tools(session, agent, extractors)
            op = llm.generate(prompt, ctx_fn(session, state["symbol"]), DeskOpinion, tools=tools)
            setattr(rs, f"{agent}_view", op.view)
            _set_opinion(rs, agent, op)
            return {"research_state": rs}
        return node

    market_node = _desk("market", prompts.MARKET, context.market_context)
    sentiment_node = _desk("sentiment", prompts.SENTIMENT, context.sentiment_context)
    technical_node = _desk("technical", prompts.TECHNICAL, context.technical_context)
    fundamentals_node = _desk("fundamental", prompts.FUNDAMENTALS, context.fundamentals_context)

    # --- PM aggregator --------------------------------------------------
    def pm_node(state: BrainState) -> dict[str, Any]:
        rs = state["research_state"]
        symbol = state["symbol"]
        opinions = [o.model_dump(mode="json") for o in rs.agent_opinions]
        pm: PMDecision = llm.generate(prompts.PM, context.pm_context(session, symbol, opinions), PMDecision)

        rs.direction = pm.direction
        rs.conviction_level = pm.conviction
        rs.pro = pm.pro
        rs.contro = pm.contro
        rs.next_check_date = date.today() + timedelta(days=max(1, pm.next_check_days))
        snap_atr = atr_from_db(session, symbol)
        # Real-time first (write-through), fallback to the latest stored bar.
        last_close = get_realtime_quote(session, symbol, live_fn=quote_fn)
        rs.current_price = last_close

        if pm.direction.is_actionable and snap_atr and last_close:
            rs.levels = atr_levels(
                last_close, snap_atr, pm.direction,
                k_entry=pm.k_entry, k_stop=pm.k_stop, k_tp=pm.k_tp,
            )
            rs.position_sizing_pct = base_risk_pct * conviction_multiplier(pm.direction)
        return {"research_state": rs, "need_more_info": bool(pm.need_more_info)}

    # --- Risk gate ------------------------------------------------------
    def risk_node(state: BrainState) -> dict[str, Any]:
        rs = state["research_state"]
        symbol = state["symbol"]

        if rs.direction is None or not rs.direction.is_actionable or rs.levels is None:
            # HOLD / nothing to execute -> the gate passes (no action).
            rs.risk.verdict = RiskVerdict.APPROVED
            rs.risk.rationale = "No actionable position; nothing to gate."
            return {"research_state": rs}

        from ..storage import repository as _repo

        portfolio = inject_portfolio_state(session)
        portfolio_value = portfolio.get("total_value", 0.0)
        heat = get_open_positions_risk(session)["heat_pct"]
        heat_max = (charter or {}).get("heat_max_pct", 0.06)
        # enrich for the VaR + sector guardrails
        portfolio["heat_pct"] = heat
        portfolio["sector"] = _repo.instrument_sector(session, symbol)
        portfolio["sector_exposure"] = _repo.sector_exposure(session)
        stop_distance = abs(rs.levels.entry_price - rs.levels.stop_loss)
        sizing = position_size(
            portfolio_value, rs.levels.entry_price, stop_distance, rs.direction,
            base_risk_pct=base_risk_pct, heat_used_pct=heat, heat_max_pct=heat_max,
        )
        guardrails = check_guardrails(
            levels=rs.levels, sizing=sizing, charter=charter, portfolio=portfolio,
            side="buy" if rs.direction.is_long else "sell",
        )
        rs.risk.guardrail_checks = guardrails

        sealed = rs.seal()
        decision: RiskDecision = llm.generate(
            prompts.RISK, context.risk_context(session, symbol, sealed, guardrails), RiskDecision,
            tools=build_desk_tools(session, "risk", extractors),
        )
        rs.risk.rationale = decision.rationale
        # Hard guardrail failure is binding regardless of the LLM's call.
        if not guardrails.get("all_ok", True):
            rs.risk.verdict = RiskVerdict.SEND_BACK
        else:
            rs.risk.verdict = decision.verdict
        return {"research_state": rs}

    def increment_revision(state: BrainState) -> dict[str, Any]:
        return {"revisions": state["revisions"] + 1, "need_more_info": False}

    # --- routing --------------------------------------------------------
    def route_after_risk(state: BrainState) -> str:
        rs = state["research_state"]
        wants_more = state.get("need_more_info") or rs.risk.verdict is RiskVerdict.SEND_BACK
        if wants_more and state["revisions"] < max_revisions:
            return "revise"
        return "end"

    # --- wire the graph -------------------------------------------------
    g = StateGraph(BrainState)
    g.add_node("market", market_node)
    g.add_node("sentiment", sentiment_node)
    g.add_node("technical", technical_node)
    g.add_node("fundamentals", fundamentals_node)
    g.add_node("pm", pm_node)
    g.add_node("risk", risk_node)
    g.add_node("revise", increment_revision)

    g.add_edge(START, "market")
    g.add_edge("market", "sentiment")
    g.add_edge("sentiment", "technical")
    g.add_edge("technical", "fundamentals")
    g.add_edge("fundamentals", "pm")
    g.add_edge("pm", "risk")
    g.add_conditional_edges("risk", route_after_risk, {"revise": "revise", "end": END})
    g.add_edge("revise", "market")
    return g.compile()


def analyze_symbol(
    session: Session,
    symbol: str,
    llm: StructuredLLM,
    *,
    max_revisions: int = 1,
    charter: Optional[dict[str, Any]] = None,
    base_risk_pct: float = 0.01,
    extractors: Optional[Extractors] = None,
) -> ResearchState:
    """Run the brain for one ticker and return the (possibly approved) thesis."""
    graph = build_brain_graph(
        session, llm, max_revisions=max_revisions, charter=charter,
        base_risk_pct=base_risk_pct, extractors=extractors,
    )
    initial: BrainState = {
        "symbol": symbol,
        "research_state": ResearchState(ticker=symbol),
        "revisions": 0,
        "need_more_info": False,
    }
    final = graph.invoke(initial)
    return final["research_state"]
