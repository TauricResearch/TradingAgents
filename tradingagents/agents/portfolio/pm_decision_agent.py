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
from tradingagents.agents.utils.historical_context import (
    find_latest_execution_failures,
    format_execution_failure_block,
)
from tradingagents.default_config import DEFAULT_CONFIG
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


def _build_pm_context(state: dict, cfg: dict) -> str:
    """Build the context block injected into the PM prompt.

    Extracts portfolio constraints and summary from *state* and *cfg*, including
    the dynamically resolved ``max_total_buy_notional`` hard ceiling so the LLM
    cannot accidentally over-spend cash even without the rescale_buys guard.

    Args:
        state: Current LangGraph node state.
        cfg: Portfolio configuration dict (e.g. min_cash_pct, max_position_pct).

    Returns:
        Multi-section context string ready to embed in the prompt.
    """
    portfolio_data_str = state.get("portfolio_data") or "{}"
    try:
        pd_raw = json.loads(portfolio_data_str)
        portfolio = pd_raw.get("portfolio") or {}
        holdings = pd_raw.get("holdings") or []
        cash = float(portfolio.get("cash", 0.0))
        total_value = float(portfolio.get("total_value") or cash)
        n_positions = len(holdings)
    except Exception:
        cash, total_value, n_positions = 0.0, 0.0, 0

    min_cash_pct = float(cfg.get("min_cash_pct", 0.05))
    max_total_buy_notional = max(0.0, cash - min_cash_pct * total_value)

    constraints_str = (
        f"- Max position size: {cfg.get('max_position_pct', 0.15):.0%}\n"
        f"- Max sector exposure: {cfg.get('max_sector_pct', 0.35):.0%}\n"
        f"- Minimum cash reserve: {min_cash_pct:.0%}\n"
        f"- Max total positions: {cfg.get('max_positions', 15)}\n"
        f"- max_total_buy_notional: ${max_total_buy_notional:,.2f} "
        f"(HARD CEILING — sum of all BUY shares*entry_price MUST NOT EXCEED this)\n"
    )
    compressed_str = json.dumps(
        {
            "cash": cash,
            "n_positions": n_positions,
            "total_value": total_value,
            "max_total_buy_notional": max_total_buy_notional,
        }
    )

    macro_brief = state.get("macro_brief") or ""
    micro_brief = state.get("micro_brief") or "No micro brief available."
    candidate_deep_dive_context = _build_candidate_deep_dive_context(
        state.get("prioritized_candidates") or "[]"
    )
    return (
        f"## Portfolio Constraints\n{constraints_str}\n\n"
        f"## Portfolio Summary\n{compressed_str}\n\n"
        f"## Input A — Macro Context & Memory\n{macro_brief}\n\n"
        f"## Input B — Direct Candidate Final Trade Decision Summaries\n{candidate_deep_dive_context}\n\n"
        f"## Input C — Micro Context & Memory\n{micro_brief}\n"
    )


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

    regime_alignment: Literal["macro-aligned", "sector-aligned", "regime-divergent", "uncorrelated"]
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

    def pm_decision_node(state: PortfolioManagerState) -> dict[str, Any]:
        analysis_date = state.get("analysis_date") or ""
        context = _build_pm_context(state, cfg)

        execution_failures = find_latest_execution_failures(
            portfolio_id=str(
                state.get("portfolio_id") or DEFAULT_CONFIG.get("default_portfolio_id") or "default"
            ),
            as_of_date=analysis_date,
        )
        execution_failure_block = format_execution_failure_block(execution_failures)
        if execution_failure_block:
            context = f"{context}\n\n{execution_failure_block}\n"

        system_message = (
            "You are a portfolio manager. Synthesize the inputs below into a JSON-only "
            "decision matching the structured schema. Every BUY must satisfy: "
            "entry_price > 0; entry_price <= max_chase_price <= limit_price; "
            "stop_loss is 5-15% below entry; take_profit is 10-30% above entry; "
            "valid_as_of is the analysis date in YYYY-MM-DD. "
            "Sum of (shares*entry_price) across BUYs MUST NOT EXCEED "
            "max_total_buy_notional shown in Portfolio Constraints. "
            "Do not buy a ticker absent from Input B (candidate summaries). "
            "IMPORTANT OUTPUT CONSTRAINTS: "
            "The forensic_report.regime_alignment field MUST use exactly one of: "
            '["macro-aligned", "sector-aligned", "regime-divergent", "uncorrelated"]. '
            "Do NOT generate descriptive phrases, portmanteau terms, or compound strings for this field. "
            'If the alignment is unclear, use "uncorrelated". '
            "Output JSON only.\n\n"
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
                # Persist the decision JSON before any downstream node can fail. This is
                # the canonical artifact for postmortem; do not gate on success of later
                # nodes.
                run_path = cfg.get("run_path")
                if not run_path:
                    # Fallback: derive a run-scoped portfolio report path so
                    # direct graph runs (CLI / tests) still satisfy PR-B1's
                    # acceptance gate when no run_path was wired through cfg.
                    # ReportStore writes require a run_id, so both
                    # state["run_id"] and analysis_date must be present.
                    state_run_id = state.get("run_id")
                    if state_run_id and analysis_date:
                        try:
                            from tradingagents.portfolio.store_factory import (
                                create_report_store,
                            )

                            run_path = str(
                                create_report_store(run_id=state_run_id).portfolio_report_dir(
                                    analysis_date
                                )
                            )
                        except Exception as exc:  # pragma: no cover - defensive
                            logger.warning(
                                "pm_decision_agent: could not derive snapshot run_path "
                                "from state run_id=%s date=%s: %s",
                                state_run_id,
                                analysis_date,
                                exc,
                            )
                if run_path:
                    try:
                        from pathlib import Path

                        snapshot_path = Path(run_path) / "portfolio_decision_snapshot.json"
                        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                        snapshot_path.write_text(decision_str)
                    except Exception as exc:
                        logger.warning(
                            "pm_decision_agent: failed to persist snapshot at %s: %s",
                            run_path,
                            exc,
                        )
                else:
                    logger.warning(
                        "pm_decision_agent: no run_path in cfg and could not derive one "
                        "from state (run_id=%s, analysis_date=%s); snapshot not persisted "
                        "(PR-B1 acceptance gate not met).",
                        state.get("run_id"),
                        analysis_date,
                    )
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
