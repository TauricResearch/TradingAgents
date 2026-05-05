"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call.  The result is rendered
back to markdown for storage in ``final_trade_decision`` so memory log,
CLI display, and saved reports continue to consume the same shape they do
today.  When a provider does not expose structured output, the agent falls
back gracefully to free-text generation.
"""

from __future__ import annotations

from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.rating import RATINGS_5_TIER, extract_rating, parse_rating
from tradingagents.agents.utils.trade_filter import compute_trade_filter
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext_with_meta,
)
from tradingagents.dataflows.config import get_config


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    rating_order = list(RATINGS_5_TIER)

    def _data_quality(error_count: int) -> str:
        if error_count <= 0:
            return "high"
        if error_count <= 2:
            return "medium"
        return "low"

    def _shift_towards_hold(rating: str, steps: int = 1) -> str:
        if rating not in rating_order:
            return "Hold"
        idx = rating_order.index(rating)
        hold_idx = rating_order.index("Hold")
        for _ in range(max(0, steps)):
            if idx < hold_idx:
                idx += 1
            elif idx > hold_idx:
                idx -= 1
        return rating_order[idx]

    def _replace_rating(text: str, new_rating: str) -> str:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.lower().lstrip().startswith("**rating**") or line.lower().lstrip().startswith("rating"):
                if ":" in line:
                    prefix = line.split(":", 1)[0]
                    lines[i] = f"{prefix}: {new_rating}"
                    return "\n".join(lines)
        return f"**Rating**: {new_rating}\n\n{text}"

    def _compute_confidence(
        *,
        rating: str,
        data_quality: str,
        error_count: int,
        structured_valid: bool,
        research_plan: str,
        trader_plan: str,
    ) -> float:
        score = 0.85
        if data_quality == "medium":
            score -= 0.1
        elif data_quality == "low":
            score -= 0.25
        score -= 0.1 * min(max(error_count, 0), 5)
        if not structured_valid:
            score -= 0.15

        rm_rating = extract_rating(research_plan or "")
        if rm_rating and rm_rating == rating:
            score += 0.05

        action = None
        tp = (trader_plan or "").lower()
        if "final transaction proposal" in tp:
            if "**buy**" in tp or " buy" in tp:
                action = "Buy"
            elif "**sell**" in tp or " sell" in tp:
                action = "Sell"
            elif "**hold**" in tp or " hold" in tp:
                action = "Hold"
        if action and action == rating:
            score += 0.05

        if score < 0.0:
            return 0.0
        if score > 1.0:
            return 1.0
        return float(score)

    def portfolio_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

        error_count = int(state.get("error_count", 0) or 0)
        data_quality = _data_quality(error_count)
        rm_structured_valid = bool(state.get("research_manager_structured_valid", False))
        trader_structured_valid = bool(state.get("trader_structured_valid", False))
        upstream_structured_valid = rm_structured_valid and trader_structured_valid
        trade_levels = state.get("trade_levels")

        reliability_constraints = ""
        if data_quality in ("low",) or error_count > 2:
            reliability_constraints = (
                "\n\n---\n\n"
                "**Reliability Constraints (must follow):**\n"
                "- If data_quality is low OR error_count > 2: "
                "you may NOT output Buy or Sell. Only Hold or Underweight are allowed.\n"
                "- If error_count >= 5: output Hold.\n"
            )

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
**Reliability Signals:**
- data_quality: {data_quality}
- error_count: {error_count}
- upstream_structured_valid: {upstream_structured_valid}
{lessons_line}
**Risk Analysts Debate History:**
{history}
{reliability_constraints}

---

Be decisive and ground every conclusion in specific evidence from the analysts.{get_language_instruction()}"""

        final_trade_decision, pm_structured_valid = invoke_structured_or_freetext_with_meta(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )

        structured_valid = bool(upstream_structured_valid and pm_structured_valid)
        rating = parse_rating(final_trade_decision)

        trade_filter_result = None
        trade_filter_score = 0.0
        trade_filter_reasons = []
        trade_filter_pass = True
        trade_filtered_out = False
        cfg = get_config()
        if cfg.get("trade_filter_enabled"):
            rm_rating = extract_rating(research_plan or "")
            trader_action = extract_rating(trader_plan or "")
            trade_filter_result = compute_trade_filter(
                trade_levels=trade_levels,
                rating=rating,
                rm_rating=rm_rating,
                trader_action=trader_action,
                data_quality=data_quality,
                error_count=error_count,
                structured_valid=structured_valid,
                threshold=float(cfg.get("trade_filter_threshold", 0.65) or 0.65),
            )
            trade_filter_score = float(trade_filter_result.get("score", 0.0) or 0.0)
            trade_filter_pass = bool(trade_filter_result.get("pass", True))
            trade_filtered_out = bool(trade_filter_result.get("filtered_out", False))
            trade_filter_reasons = list(trade_filter_result.get("hard_reject_reasons", [])) + list(
                trade_filter_result.get("reasons", [])
            )
            if trade_filtered_out and rating in ("Buy", "Sell"):
                rating = "Hold"

        if error_count >= 5:
            rating = "Hold"
        elif (data_quality == "low") or (error_count > 2):
            if rating in ("Buy", "Sell"):
                rating = _shift_towards_hold(rating, steps=2)
            if rating not in ("Hold", "Underweight"):
                rating = _shift_towards_hold(rating, steps=1)

        confidence_score = _compute_confidence(
            rating=rating,
            data_quality=data_quality,
            error_count=error_count,
            structured_valid=structured_valid,
            research_plan=research_plan,
            trader_plan=trader_plan,
        )

        final_trade_decision = _replace_rating(final_trade_decision, rating)
        final_trade_decision = (
            f"{final_trade_decision}\n\n"
            f"**Data Quality**: {data_quality}\n"
            f"**Error Count**: {error_count}\n"
            f"**Structured Valid**: {structured_valid}\n"
            f"**Confidence**: {confidence_score:.2f}\n"
            f"**Trade Filter Score**: {trade_filter_score:.2f}\n"
            f"**Trade Filter Pass**: {trade_filter_pass}\n"
            f"**Trade Filtered Out**: {trade_filtered_out}"
        )

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
            "portfolio_manager_structured_valid": pm_structured_valid,
            "structured_valid": structured_valid,
            "data_quality": data_quality,
            "error_count": error_count,
            "confidence_score": confidence_score,
            "trade_levels": trade_levels,
            "trade_filter_score": trade_filter_score,
            "trade_filter_pass": trade_filter_pass,
            "trade_filter_reasons": trade_filter_reasons,
            "trade_filtered_out": trade_filtered_out,
            "trade_filter_details": trade_filter_result,
        }

    return portfolio_manager_node
