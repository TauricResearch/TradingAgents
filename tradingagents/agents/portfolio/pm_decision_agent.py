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


def create_pm_decision_agent(llm):
    """Create a PM decision agent node.

    Args:
        llm: A LangChain chat model instance (deep_think recommended).

    Returns:
        A node function ``pm_decision_node(state)`` compatible with LangGraph.
    """

    def pm_decision_node(state):
        analysis_date = state.get("analysis_date") or ""
        portfolio_data_str = state.get("portfolio_data") or "{}"
        risk_metrics_str = state.get("risk_metrics") or "{}"
        holding_reviews_str = state.get("holding_reviews") or "{}"
        prioritized_candidates_str = state.get("prioritized_candidates") or "[]"

        context = f"""## Portfolio Data
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
            "Given the risk metrics, holding reviews, and prioritized investment candidates, "
            "produce a structured JSON investment decision. "
            "Consider: reducing risk where metrics are poor, acting on SELL recommendations, "
            "and adding positions in high-conviction candidates that pass constraints. "
            "Output ONLY valid JSON matching this exact schema:\n"
            "{\n"
            '  "sells": [{"ticker": "...", "shares": 0.0, "rationale": "..."}],\n'
            '  "buys": [{"ticker": "...", "shares": 0.0, "price_target": 0.0, '
            '"sector": "...", "rationale": "...", "thesis": "..."}],\n'
            '  "holds": [{"ticker": "...", "rationale": "..."}],\n'
            '  "cash_reserve_pct": 0.10,\n'
            '  "portfolio_thesis": "...",\n'
            '  "risk_summary": "..."\n'
            "}\n\n"
            "IMPORTANT: Output ONLY valid JSON. Start your response with '{' and end with '}'. "
            "Do NOT use markdown code fences. Do NOT include any explanation before or after the JSON.\n\n"
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
