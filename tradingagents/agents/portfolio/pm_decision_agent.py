"""Portfolio Manager Decision Agent.

Pure reasoning LLM agent (no tools).  Synthesizes macro and micro briefs into a
fully auditable, structured investment decision via Pydantic-schema-driven output.

Pattern: ``create_pm_decision_agent(llm)`` → closure (macro_synthesis pattern).
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from datetime import date
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tradingagents.agents.utils.circuit_breaker import circuit_breaker_from_config
from tradingagents.portfolio.portfolio_states import PortfolioManagerState

logger = logging.getLogger(__name__)

_NEWLINE_C_PERCENT_ARTIFACT = re.compile(r"%\s*\nc\b")


def _parse_candidates_safely(raw: str) -> list[dict[str, Any]]:
    """Parse prioritized candidates JSON, returning an empty list on failure."""
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "pm_decision_agent: could not parse prioritized_candidates (first 100): %s",
            raw[:100],
        )
        return []
    return parsed if isinstance(parsed, list) else []


def _build_candidate_deep_dive_context(prioritized_candidates_raw: str) -> str:
    """Build a compact JSON block of candidate final trade decisions for the PM."""
    candidates = _parse_candidates_safely(prioritized_candidates_raw)
    summarized: list[dict[str, object]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_final_trade_decision_summary = str(
            candidate.get("candidate_final_trade_decision_summary") or ""
        ).strip()
        if not candidate_final_trade_decision_summary:
            continue
        summarized.append(
            {
                "ticker": candidate.get("ticker", ""),
                "instrument_key": candidate.get("instrument_key", ""),
                "conviction": candidate.get("conviction", ""),
                "thesis_angle": candidate.get("thesis_angle", ""),
                "priority_score": candidate.get("priority_score"),
                "candidate_final_trade_decision_summary": candidate_final_trade_decision_summary,
            }
        )
    if not summarized:
        return "No direct candidate final trade decision summaries available."
    return json.dumps(summarized, indent=2)


# ---------------------------------------------------------------------------
# Pydantic output schema
# ---------------------------------------------------------------------------


def _contains_newline_c_artifact(value: Any) -> bool:
    if isinstance(value, str):
        return _NEWLINE_C_PERCENT_ARTIFACT.search(value) is not None
    if isinstance(value, dict):
        return any(_contains_newline_c_artifact(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_newline_c_artifact(item) for item in value)
    return False


class _PMBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _reject_newline_c_artifact(cls, data: Any) -> Any:
        if _contains_newline_c_artifact(data):
            raise ValueError("structured PM output contains newline-c artifact")
        return data


class ForensicReport(_PMBaseModel):
    """Audit trail for the PM's decision confidence and risk posture."""

    regime_alignment: str
    key_risks: list[str]
    decision_confidence: Literal["high", "medium", "low"]
    position_sizing_rationale: str


class BuyOrder(_PMBaseModel):
    """A fully justified buy order with executable entry and risk parameters."""

    ticker: str
    shares: float
    entry_price: float = Field(gt=0)
    limit_price: float = Field(gt=0)
    max_chase_price: float = Field(gt=0)
    order_type: Literal["limit"]
    valid_as_of: str
    price_target: float
    stop_loss: float
    take_profit: float
    sector: str
    rationale: str
    thesis: str
    macro_alignment: str
    memory_note: str
    position_sizing_logic: str

    @field_validator("valid_as_of")
    @classmethod
    def _validate_valid_as_of(cls, value: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("valid_as_of must use strict YYYY-MM-DD format")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                "valid_as_of must be a real calendar date in YYYY-MM-DD format"
            ) from exc
        return value

    @model_validator(mode="after")
    def _validate_buy_price_relationships(self) -> BuyOrder:
        if self.entry_price > self.limit_price:
            raise ValueError("entry_price must be less than or equal to limit_price")
        if self.entry_price > self.max_chase_price:
            raise ValueError("entry_price must be less than or equal to max_chase_price")
        if self.max_chase_price > self.limit_price:
            raise ValueError("max_chase_price must be less than or equal to limit_price")
        return self


class SellOrder(_PMBaseModel):
    """A sell order with macro-driven flag."""

    ticker: str
    shares: float
    rationale: str
    macro_driven: bool


class HoldOrder(_PMBaseModel):
    """A hold decision with rationale."""

    ticker: str
    rationale: str


class PMDecisionSchema(_PMBaseModel):
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
    llm: Any,
    config: dict[str, Any] | None = None,
    macro_memory: Any = None,
    micro_memory: Any = None,
) -> Callable[[PortfolioManagerState], dict[str, Any]]:
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
    breaker = circuit_breaker_from_config(cfg)
    constraints_str = (
        f"- Max position size: {cfg.get('max_position_pct', 0.15):.0%}\n"
        f"- Max sector exposure: {cfg.get('max_sector_pct', 0.35):.0%}\n"
        f"- Minimum cash reserve: {cfg.get('min_cash_pct', 0.05):.0%}\n"
        f"- Max total positions: {cfg.get('max_positions', 15)}\n"
    )

    def pm_decision_node(state: PortfolioManagerState) -> dict[str, Any]:
        analysis_date = state.get("analysis_date") or ""

        # Read brief fields written by upstream summary agents
        _macro_brief_raw = state.get("macro_brief") or ""
        macro_brief = _macro_brief_raw or ""
        micro_brief = state.get("micro_brief") or "No micro brief available."
        candidate_deep_dive_context = _build_candidate_deep_dive_context(
            state.get("prioritized_candidates") or "[]"
        )

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
            f"## Input B — Direct Candidate Final Trade Decision Summaries\n{candidate_deep_dive_context}\n\n"
            f"## Input C — Micro Context & Memory\n{micro_brief}\n"
        )

        system_message = (
            "You are a portfolio manager making final, risk-adjusted investment decisions. "
            "You receive three inputs: (A) a macro regime brief with memory, "
            "(B) direct candidate final trade decision summaries extracted from completed ticker analyses, "
            "and (C) a micro brief with per-ticker signals and memory. Synthesize these inputs into a Forensic Execution "
            "Dashboard — a fully auditable decision plan where every trade is justified by both "
            "macro alignment and micro thesis.\n\n"
            "The direct candidate final trade decision summaries are the most authoritative source for new candidate buys. "
            "Use them explicitly when evaluating candidate entries, and ensure your rationale reflects that evidence. "
            "The micro brief is built from completed ticker deep-dive analyses and current holdings context. "
            "Use both the direct candidate final trade decision summaries and the micro brief as the authoritative basis for buy, hold, and sell decisions. "
            "Do not recommend a new buy for any ticker that is not supported by the completed deep-dive input.\n\n"
            "## CONSTRAINTS COMPLIANCE:\n"
            "You MUST ensure all buys adhere to the portfolio constraints. "
            "If a high-conviction candidate exceeds max position size or sector limit, "
            "adjust shares downward to fit. For every BUY: set stop_loss (5-15% below entry) "
            "and take_profit (10-30% above entry).\n\n"
            "Every BUY must be executable as a limit order. "
            "Set entry_price to the price assumed by the candidate thesis, limit_price to the highest allowed execution price, "
            "and max_chase_price to the highest price where the risk/reward still matches the thesis. "
            "All three prices must be positive and satisfy entry_price <= max_chase_price <= limit_price. "
            "If the candidate summary says not to chase above a level, max_chase_price and limit_price must not exceed that level. "
            "Never use price_target as an entry price. "
            "Set valid_as_of to the portfolio analysis date in strict YYYY-MM-DD format.\n\n"
            "### STRICT OUTPUT REQUIREMENTS:\n"
            "For every BUY, you MUST provide all required fields in the schema:\n"
            "- ticker\n"
            "- shares\n"
            "- entry_price (numeric float > 0; price used for sizing and risk/reward)\n"
            "- limit_price (numeric float > 0; execution must not buy above this level)\n"
            "- max_chase_price (numeric float > 0; must be >= entry_price and <= limit_price)\n"
            "- order_type (must be the literal string 'limit')\n"
            "- valid_as_of (strict YYYY-MM-DD date string for the analysis date)\n"
            "- price_target (numeric float)\n"
            "- stop_loss (numeric float)\n"
            "- take_profit (numeric float)\n"
            "- sector\n"
            "- rationale (DETAILED string)\n"
            "- thesis (DETAILED string)\n"
            "- macro_alignment (how it fits the current regime)\n"
            "- memory_note (any relevant historical lesson)\n"
            "- position_sizing_logic (why you chose this amount of shares)\n\n"
            "Failure to include any of these fields will cause a system error.\n\n"
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
        breaker.assert_available("pm_decision_agent")
        structured_llm = llm.with_structured_output(PMDecisionSchema)
        chain = prompt | structured_llm

        attempts = 3
        last_exc = None
        extra_messages = []
        for attempt in range(1, attempts + 1):
            try:
                # On retries, we inject a reminder message
                input_data = {"messages": extra_messages}
                result = chain.invoke(input_data)
                decision_str = result.model_dump_json()
                breaker.record_success("pm_decision_agent")
                break
            except Exception as exc:
                last_exc = exc
                breaker.record_failure("pm_decision_agent", f"{type(exc).__name__}: {exc}")
                logger.warning(
                    "pm_decision_agent: structured output attempt %d/%d failed: %s",
                    attempt,
                    attempts,
                    exc,
                )
                if attempt < attempts:
                    # Append a hint for the next attempt
                    extra_messages.append(
                        HumanMessage(
                            content=(
                                f"Your previous response failed validation: {exc}\n\n"
                                "Please ensure EVERY BuyOrder contains all required fields: "
                                "entry_price, limit_price, max_chase_price, order_type, valid_as_of, "
                                "price_target, rationale, thesis, macro_alignment, memory_note, "
                                "and position_sizing_logic. Every BUY must be executable as a limit order, "
                                "valid_as_of must use strict YYYY-MM-DD format, and buy prices must satisfy "
                                "entry_price <= max_chase_price <= limit_price with all values > 0. "
                                "Do not omit any of them."
                            )
                        )
                    )
                    time.sleep(1.0)
                    continue

                raise RuntimeError(
                    f"pm_decision_agent: structured output failed after {attempts} attempts "
                    f"({type(last_exc).__name__}: {last_exc})"
                ) from last_exc

        # with_structured_output returns the Pydantic model directly, not an AIMessage.
        # Wrap in a synthetic AIMessage so downstream message-history nodes stay consistent.
        synthetic_msg = AIMessage(content=decision_str)
        return {
            "messages": [synthetic_msg],
            "pm_decision": decision_str,
            "sender": "pm_decision_agent",
        }

    return pm_decision_node
