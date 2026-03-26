"""Portfolio Manager Decision Agent.

Pure reasoning LLM agent (no tools).  Synthesizes macro and micro briefs into a
fully auditable, structured investment decision via Pydantic-schema-driven output.

Pattern: ``create_pm_decision_agent(llm)`` → closure (macro_synthesis pattern).
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel

from tradingagents.agents.utils.json_utils import extract_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic output schema
# ---------------------------------------------------------------------------


class ForensicReport(BaseModel):
    """Audit trail for the PM's decision confidence and risk posture."""

    regime_alignment: str
    key_risks: list[str]
    decision_confidence: Literal["high", "medium", "low"]
    position_sizing_rationale: str


class BuyOrder(BaseModel):
    """A fully justified buy order with risk parameters."""

    ticker: str
    shares: float
    price_target: float
    stop_loss: float
    take_profit: float
    sector: str
    rationale: str
    thesis: str
    macro_alignment: str
    memory_note: str
    position_sizing_logic: str


class SellOrder(BaseModel):
    """A sell order with macro-driven flag."""

    ticker: str
    shares: float
    rationale: str
    macro_driven: bool


class HoldOrder(BaseModel):
    """A hold decision with rationale."""

    ticker: str
    rationale: str


class PMDecisionSchema(BaseModel):
    """Full PM decision output — structured and auditable."""

    macro_regime: Literal["risk-on", "risk-off", "neutral", "transition"]
    regime_alignment_note: str
    sells: list[SellOrder]
    buys: list[BuyOrder]
    holds: list[HoldOrder]
    cash_reserve_pct: float
    portfolio_thesis: str
    risk_summary: str
    forensic_report: ForensicReport


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_pm_decision_agent(
    llm,
    config: dict | None = None,
    macro_memory=None,
    micro_memory=None,
):
    """Create a PM decision agent node.

    Args:
        llm: A LangChain chat model instance (deep_think recommended).
        config: Portfolio configuration dictionary containing constraints.
        macro_memory: Reserved for future direct retrieval; briefs come via state.
        micro_memory: Reserved for future direct retrieval; briefs come via state.

    Returns:
        A node function ``pm_decision_node(state)`` compatible with LangGraph.
    """
    cfg = config or {}
    constraints_str = (
        f"- Max position size: {cfg.get('max_position_pct', 0.15):.0%}\n"
        f"- Max sector exposure: {cfg.get('max_sector_pct', 0.35):.0%}\n"
        f"- Minimum cash reserve: {cfg.get('min_cash_pct', 0.05):.0%}\n"
        f"- Max total positions: {cfg.get('max_positions', 15)}\n"
    )

    def pm_decision_node(state):
        analysis_date = state.get("analysis_date") or ""

        # Read brief fields written by upstream summary agents
        _macro_brief_raw = state.get("macro_brief") or ""
        if not _macro_brief_raw or "NO DATA AVAILABLE" in _macro_brief_raw:
            # Macro scanner failed — give PM explicit guidance rather than passing sentinel
            macro_brief = (
                "MACRO DATA UNAVAILABLE: No scanner output was produced. "
                "Proceed with micro brief only. Adopt a conservative posture: "
                "hold existing positions and avoid new buys unless micro thesis is very strong."
            )
        else:
            macro_brief = _macro_brief_raw
        micro_brief = state.get("micro_brief") or "No micro brief available."

        # Build compressed portfolio summary — avoid passing the full blob
        portfolio_data_str = state.get("portfolio_data") or "{}"
        try:
            pd_raw = json.loads(portfolio_data_str)
            portfolio = pd_raw.get("portfolio") or {}
            holdings = pd_raw.get("holdings") or []
            compressed = {
                "cash": portfolio.get("cash", 0.0),
                "n_positions": len(holdings),
                "total_value": portfolio.get("total_value"),
            }
            compressed_str = json.dumps(compressed)
        except Exception:
            # Fallback: truncated raw string keeps token count bounded
            compressed_str = portfolio_data_str[:200]

        context = (
            f"## Portfolio Constraints\n{constraints_str}\n\n"
            f"## Portfolio Summary\n{compressed_str}\n\n"
            f"## Input A — Macro Context & Memory\n{macro_brief}\n\n"
            f"## Input B — Micro Context & Memory\n{micro_brief}\n"
        )

        system_message = (
            "You are a portfolio manager making final, risk-adjusted investment decisions. "
            "You receive two inputs: (A) a macro regime brief with memory, and (B) a micro brief "
            "with per-ticker signals and memory. Synthesize A and B into a Forensic Execution "
            "Dashboard — a fully auditable decision plan where every trade is justified by both "
            "macro alignment and micro thesis.\n\n"
            "## CONSTRAINTS COMPLIANCE:\n"
            "You MUST ensure all buys adhere to the portfolio constraints. "
            "If a high-conviction candidate exceeds max position size or sector limit, "
            "adjust shares downward to fit. For every BUY: set stop_loss (5-15% below entry) "
            "and take_profit (10-30% above entry). "
            "Every buy must have macro_alignment (how it fits the regime), "
            "memory_note (any relevant historical lesson), and position_sizing_logic.\n\n"
            f"{context}"
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    " For your reference, the current date is {current_date}.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names="none")
        prompt = prompt.partial(current_date=analysis_date)

        # Primary path: structured output via Pydantic schema
        structured_llm = llm.with_structured_output(PMDecisionSchema)
        chain = prompt | structured_llm

        try:
            result = chain.invoke(state["messages"])
            decision_str = result.model_dump_json()
        except Exception as exc:
            logger.warning(
                "pm_decision_agent: structured output failed (%s); falling back to raw", exc
            )
            # Fallback: plain LLM + extract_json
            chain_raw = prompt | llm
            raw_result = chain_raw.invoke(state["messages"])
            raw = raw_result.content or "{}"
            try:
                parsed = extract_json(raw)
                decision_str = json.dumps(parsed)
            except (ValueError, json.JSONDecodeError):
                decision_str = raw
            return {
                "messages": [raw_result],
                "pm_decision": decision_str,
                "sender": "pm_decision_agent",
            }

        # with_structured_output returns the Pydantic model directly, not an AIMessage.
        # Wrap in a synthetic AIMessage so downstream message-history nodes stay consistent.
        synthetic_msg = AIMessage(content=decision_str)
        return {
            "messages": [synthetic_msg],
            "pm_decision": decision_str,
            "sender": "pm_decision_agent",
        }

    return pm_decision_node
