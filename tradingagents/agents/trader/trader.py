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
                    "The user is new to finance and is reading this to LEARN as well as "
                    "act. Treat every output field that the user will read (especially "
                    "`reasoning`, `position_sizing`, and any explanation around "
                    "entry_price / stop_loss / take_profit) as if you're explaining to a "
                    "smart friend who has never traded. Do NOT assume any baseline of "
                    "investing vocabulary — including the supposedly basic terms: PE, "
                    "EPS, market cap, support/resistance, beta, bull/bear, dividend "
                    "yield, free cash flow, margin, multiple, drawdown, ATR, "
                    "stop-loss, take-profit, breakout, catalyst, re-rating, guidance.\n\n"
                    "MANDATORY: the FIRST time any such term appears in your output, "
                    "gloss it inline in plain English, in parentheses. Use the real "
                    "term — don't dumb it down — but make sure a beginner can follow.\n\n"
                    "Examples of the format you must use:\n"
                    "  • '...anchored at a technical support level (a price the stock has "
                    "    repeatedly bounced from in the past, where buyers tend to step in) "
                    "    of $148...'\n"
                    "  • '...the stop_loss (the price at which we'd cut the position to "
                    "    cap the loss) is set at...'\n"
                    "  • '...ATR (Average True Range — roughly, how much this stock moves "
                    "    in a typical day; here, ~$3) so a normal day's wiggle won't trip "
                    "    the stop...'\n"
                    "  • '...P/E ratio (price-to-earnings, what you pay for £1 of annual "
                    "    profit) of 28...'\n\n"
                    "After the first gloss in a given output, you can use the term plainly. "
                    "Do not skip the gloss because 'everyone knows it' — the user explicitly "
                    "does not. Keep the analytical substance fully intact; just make sure "
                    "every term lands.\n\n"
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
