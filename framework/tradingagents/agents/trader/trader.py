# Modified for A-share position management; see repository NOTICE.
"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from tradingagents.a_share import render_a_share_context
from tradingagents.agents.schemas import (
    PositionManagementProposal,
    TraderProposal,
    render_position_management_proposal,
    render_trader_proposal,
)
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")
    a_share_structured_llm = bind_structured(
        llm, PositionManagementProposal, "A-share Position Trader"
    )

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = get_instrument_context_from_state(state)
        investment_plan = state["investment_plan"]
        is_a_share = state.get("asset_type") == "a_share"
        a_share_context = render_a_share_context(state.get("a_share_context"))

        if is_a_share:
            system_content = (
                "You are an A-share position-management trader. Choose exactly one "
                "of Add / Slight Add / Hold / Reduce / Exit. Convert the research "
                "plan into a target portfolio weight and executable order. Enforce "
                "T+1, 100-share buy lots, board-specific price limits, fees, and "
                "concentration risk. Never use generic Buy/Sell terminology."
                + get_language_instruction()
            )
            user_content = (
                f"{instrument_context}\n{a_share_context}\n\n"
                f"Research plan:\n{investment_plan}\n\n"
                "Use the deterministic matrix as the baseline. If bought_today is "
                "true, do not propose selling those shares today."
            )
            active_structured = a_share_structured_llm
            renderer = render_position_management_proposal
        else:
            system_content = (
                "You are a trading agent analyzing market data to make investment decisions. "
                "Based on your analysis, provide a specific recommendation to buy, sell, or hold. "
                "Anchor your reasoning in the analysts' reports and the research plan."
                + get_language_instruction()
            )
            user_content = (
                f"Based on a comprehensive analysis by a team of analysts, here is an investment "
                f"plan tailored for {company_name}. {instrument_context} This plan incorporates "
                f"insights from current technical market trends, macroeconomic indicators, and "
                f"social media sentiment. Use this plan as a foundation for evaluating your next "
                f"trading decision.\n\nProposed Investment Plan: {investment_plan}\n\n"
                f"Leverage these insights to make an informed and strategic decision."
            )
            active_structured = structured_llm
            renderer = render_trader_proposal

        messages = [
            {
                "role": "system",
                "content": system_content,
            },
            {
                "role": "user",
                "content": user_content,
            },
        ]

        trader_plan = invoke_structured_or_freetext(
            active_structured,
            llm,
            messages,
            renderer,
            "Trader",
        )

        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
