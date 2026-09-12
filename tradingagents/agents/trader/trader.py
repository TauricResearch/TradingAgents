"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import TraderProposal, render_trader_proposal
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.dataflows import config


def build_trader_messages(
    state: Mapping[str, Any], *, output_language: str
) -> list[dict[str, str]]:
    """Build Trader messages without invoking the model."""
    company_name = state["company_of_interest"]
    # The research plan digests the debate but loses exact price structure;
    # give the Trader the technical market report so entry/stop levels are
    # grounded in real ATR / support-resistance / current price (#1167). The
    # report is empty when the user did not select the market analyst, so
    # only offer it (and the grounding instruction) when it has content.
    market_report = (state["market_report"] or "").strip()
    if market_report:
        grounding = (
            "Ground concrete price levels (entry, stop-loss, position sizing) in the technical "
            "market report's price structure -- current price, support/resistance, ATR, and "
            "volatility -- and use the research plan for direction and strategy. "
        )
        report_section = f"Technical Market Report:\n{market_report}\n\n"
    else:
        grounding = ""
        report_section = ""
    return [
        {
            "role": "system",
            "content": (
                "You are a trading agent analyzing market data to make investment decisions. "
                "Based on your analysis, provide a specific recommendation to buy, sell, or hold. "
                + grounding
                # Entry/stop are numeric price fields. Asking for concrete
                # levels invites a percentage ("15%"), which is not a price
                # and fails the structured parse (#1288).
                + "State entry price and stop-loss as absolute price levels in the "
                "instrument's quote currency (for example 189.5), never a percentage "
                "or a range; convert a percentage distance to the price level it "
                "implies, or omit the field if you cannot state a number. "
                + NO_EXTERNAL_TOOLS
                + get_language_instruction(output_language)
            ),
        },
        {
            "role": "user",
            "content": (
                f"Here is the research team's investment plan for {company_name}. "
                f"{get_instrument_context_from_state(state)}\n\n"
                f"{report_section}"
                f"Proposed Investment Plan:\n{state['investment_plan']}\n\n"
                f"Make an informed, strategic trading decision."
            ),
        },
    ]


def apply_trader_output(state: Mapping[str, Any], output: str) -> dict[str, Any]:
    return {"trader_investment_plan": output}


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state, name):
        language = config.get_config().get("output_language", "English")
        trader_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            build_trader_messages(state, output_language=language),
            render_trader_proposal,
            "Trader",
        )
        return apply_trader_output(state, trader_plan) | {
            "messages": [AIMessage(content=trader_plan)],
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
