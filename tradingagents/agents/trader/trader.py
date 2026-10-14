"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import TraderProposal, render_trader_proposal
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_investor_profile_instruction,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = get_instrument_context_from_state(state)
        investment_plan = state["investment_plan"]
        # The research plan digests the debate but loses exact price structure;
        # give the Trader the technical market report so staged entry prices
        # are grounded in real support / moving averages / current price
        # (#1167). The report is empty when the user did not select the market
        # analyst, so only offer it (and the grounding instruction) when it has
        # content.
        market_report = (state["market_report"] or "").strip()

        if market_report:
            grounding = (
                "Ground concrete price levels (entry and add-on prices) in the technical "
                "market report's price structure -- current price, support/resistance and "
                "moving averages -- and use the research plan for direction and strategy. "
            )
            report_section = f"Technical Market Report:\n{market_report}\n\n"
        else:
            grounding = ""
            report_section = ""

        messages = [
            {
                "role": "system",
                "content": (
                    "You turn the research team's plan into a concrete purchase plan for a "
                    "long-term investor. Based on your analysis, provide a specific "
                    "recommendation to buy, sell, or hold. "
                    + grounding
                    # Entry/add-on are numeric price fields. Asking for concrete
                    # levels invites a percentage ("15%"), which is not a price
                    # and fails the structured parse (#1288).
                    + "State entry and add-on prices as absolute price levels in the "
                    "instrument's quote currency (for example 9.85), never a percentage "
                    "or a range; convert a percentage distance to the price level it "
                    "implies, or omit the field if you cannot state a number. "
                    "Give the number of 100-share board lots one purchase buys at the "
                    "entry price. Do not set a stop-loss: describe the conditions that "
                    "would break the investment thesis instead. "
                    + NO_EXTERNAL_TOOLS
                    + get_investor_profile_instruction() + get_language_instruction()
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Here is the research team's investment plan for {company_name}. "
                    f"{instrument_context}\n\n"
                    f"{report_section}"
                    f"Proposed Investment Plan:\n{investment_plan}\n\n"
                    f"Make an informed, strategic trading decision."
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
