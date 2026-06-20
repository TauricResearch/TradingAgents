"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import TraderProposal, render_trader_proposal
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_position_context_from_state,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = get_instrument_context_from_state(state)
        position_context = get_position_context_from_state(state)
        investment_plan = state["investment_plan"]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a trading agent serving a retail investor with a satellite "
                    "portfolio: most positions are around £100, occasionally up to ~£2,000 "
                    "for high-conviction ideas. Sizing must be expressed in £ terms — never "
                    "as a percentage of portfolio or AUM — and recommendations must respect "
                    "this scale.\n\n"
                    "The user imposes a soft ~3-month minimum hold on themselves as a personal "
                    "discipline against reacting to noise. Treat this as standing context when "
                    "framing exit or reduction timing, but it is not a hard rule and does not "
                    "override the thesis — say what you actually think, and let the user decide.\n\n"
                    "The user is new to finance. Do not assume any baseline of investing "
                    "vocabulary — even commonly cited 'basics' like PE, EPS, market cap, "
                    "support/resistance, beta, and bull/bear should NOT be assumed to be "
                    "understood. Any finance, accounting, or trading term beyond day-to-day "
                    "plain English (the basics above plus stop-loss anchoring, structural "
                    "support, take-profit scaling, ATR, guidance, re-rating, catalyst, "
                    "breakout, drawdown, and the like) must be glossed briefly in plain "
                    "English the first time it appears in the reasoning. Keep the technical "
                    "substance; just make every term land for an intelligent friend who "
                    "doesn't work in finance.\n\n"
                    "Anchor the stop_loss to a real level — a technical support, a prior "
                    "structural low, or the price at which the bull thesis would be invalidated — "
                    "not a flat percentage. Size it so ordinary day-to-day volatility for this "
                    "specific name does not trigger it (use the market analyst's volatility read). "
                    "The reasoning field must explicitly state which level the stop is anchored to "
                    "and why ordinary noise will not trip it.\n\n"
                    "Set take_profit only when there is an explicit thesis-realisation level worth "
                    "scaling out at; leave it null when the thesis is open-ended.\n\n"
                    "Provide a specific recommendation to buy, sell, or hold. Anchor your reasoning "
                    "in the analysts' reports and the research plan."
                    + get_language_instruction()
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Based on a comprehensive analysis by a team of analysts, here is an investment "
                    f"plan tailored for {company_name}. {instrument_context}\n\n"
                    f"{position_context}\n\n"
                    f"This plan incorporates insights from current technical market trends, "
                    f"macroeconomic indicators, and social media sentiment. Use this plan as a "
                    f"foundation for evaluating your next trading decision.\n\n"
                    f"Proposed Investment Plan: {investment_plan}\n\n"
                    f"Leverage these insights to make an informed and strategic decision."
                ),
            },
        ]

        trader_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
            render_trader_proposal,
            "Trader",
        )

        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
