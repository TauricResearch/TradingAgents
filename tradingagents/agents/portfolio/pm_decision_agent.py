"""Portfolio Manager Decision Agent.

Pure reasoning LLM agent (no tools).  Synthesizes risk metrics, holding
reviews, and prioritized candidates into a structured investment decision.

Pattern: ``create_pm_decision_agent(llm)`` → closure (macro_synthesis pattern).
"""

from __future__ import annotations

import json
import logging

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.json_utils import extract_json

logger = logging.getLogger(__name__)


def create_pm_decision_agent(llm, config: dict | None = None):
    """Create a PM decision agent node.

    Args:
        llm: A LangChain chat model instance (deep_think recommended).
        config: Portfolio configuration dictionary containing constraints.

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
        portfolio_data_str = state.get("portfolio_data") or "{}"
        risk_metrics_str = state.get("risk_metrics") or "{}"
        holding_reviews_str = state.get("holding_reviews") or "{}"
        prioritized_candidates_str = state.get("prioritized_candidates") or "[]"

        context = f"""## Portfolio Constraints
{constraints_str}

## Portfolio Data
{portfolio_data_str}

## Risk Metrics
{risk_metrics_str}

## Holding Reviews
{holding_reviews_str}

## Prioritized Candidates
{prioritized_candidates_str}
"""

        system_message = (
            "You are a portfolio manager making final investment decisions. "
            "Given the constraints, risk metrics, holding reviews, and prioritized investment candidates, "
            "produce a structured JSON investment decision. "
            "## CONSTRAINTS COMPLIANCE:\n"
            "You MUST ensure your suggested buys and position sizes adhere to the portfolio constraints. "
            "If a high-conviction candidate would exceed the max position size or sector limit, "
            "YOU MUST adjust the suggested 'shares' downward to fit within the limit. "
            "Do not suggest buys that you know will be rejected by the risk engine.\n\n"
            "Consider: reducing risk where metrics are poor, acting on SELL recommendations, "
            "and adding positions in high-conviction candidates that pass constraints. "
            "For every BUY you MUST set a stop_loss price (maximum acceptable loss level, "
            "typically 5-15% below entry) and a take_profit price (expected sell target, "
            "typically 10-30% above entry based on your thesis). "
            "Output ONLY valid JSON matching this exact schema:\n"
            "{\n"
            '  "sells": [{"ticker": "...", "shares": 0.0, "rationale": "..."}],\n'
            '  "buys": [{"ticker": "...", "shares": 0.0, "price_target": 0.0, '
            '"stop_loss": 0.0, "take_profit": 0.0, '
            '"sector": "...", "rationale": "...", "thesis": "..."}],\n'
            '  "holds": [{"ticker": "...", "rationale": "..."}],\n'
            '  "cash_reserve_pct": 0.10,\n'
            '  "portfolio_thesis": "...",\n'
            '  "risk_summary": "..."\n'
            "}\n\n"
            "IMPORTANT: Output ONLY valid JSON. Start your response with '{' and end with '}'. "
            "Do NOT use markdown code fences. Do NOT include any explanation or preamble before or after the JSON.\n\n"
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

        chain = prompt | llm
        result = chain.invoke(state["messages"])

        raw = result.content or "{}"
        try:
            parsed = extract_json(raw)
            decision_str = json.dumps(parsed)
        except (ValueError, json.JSONDecodeError):
            logger.warning(
                "pm_decision_agent: could not extract JSON; storing raw (first 200): %s",
                raw[:200],
            )
            decision_str = raw

        return {
            "messages": [result],
            "pm_decision": decision_str,
            "sender": "pm_decision_agent",
        }

    return pm_decision_node
