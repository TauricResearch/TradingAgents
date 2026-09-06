"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import TraderProposal, render_trader_proposal
from tradingagents.agents.utils.agent_utils import (
    external_signal_prompt_block,
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)

_NO_POSITION_INSTRUCTION = (
    "You are a trading agent analyzing market data to make investment decisions. "
    "There is no existing position — every call is a fresh entry, typically an "
    "options position opened today and closed at or shortly after tomorrow's open, "
    "so the case for entering has to rest on what changes by then, not on a "
    "multi-week or next-quarter development. "
    "Based on your analysis, provide a specific recommendation to buy, sell, or hold."
)

_DEBATE_SKIPPED_PLACEHOLDER = (
    "N/A — debate ablation run: Bull/Bear Researcher debate and Research Manager "
    "synthesis were skipped for this run; the Trader read the analysts' reports "
    "directly instead."
)


def create_trader(llm, debate_enabled: bool = True):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = get_instrument_context_from_state(state)
        # TradingAgents#30: the upstream signal (and its direction) is stated
        # to the Trader directly -- it must not depend on whether an analyst
        # happened to carry it into a report -- and contradicting it or
        # sitting on Hold now has to be justified in `reasoning`.
        external_block = external_signal_prompt_block(state, require_justification=True)
        external_section = f"\n\n{external_block}" if external_block else ""
        # The research plan digests the debate but loses exact price structure;
        # give the Trader the technical market report so entry/stop levels are
        # grounded in real ATR / support-resistance / current price (#1167). The
        # report is empty when the user did not select the market analyst, so
        # only offer it (and the grounding instruction) when it has content.
        market_report = (state.get("market_report") or "").strip()
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

        if debate_enabled:
            investment_plan = state["investment_plan"]
            messages = [
                {
                    "role": "system",
                    "content": (
                        _NO_POSITION_INSTRUCTION
                        + " Anchor your reasoning in the analysts' reports and the research plan. "
                        + grounding
                        + NO_EXTERNAL_TOOLS
                        + get_language_instruction()
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Based on a comprehensive analysis by a team of analysts, here is an investment "
                        f"plan tailored for {company_name}. {instrument_context} This plan incorporates "
                        f"insights from current technical market trends, macroeconomic indicators, and "
                        f"social media sentiment. Use this plan as a foundation for evaluating your next "
                        f"trading decision.\n\n"
                        f"{report_section}"
                        f"Proposed Investment Plan: {investment_plan}"
                        f"{external_section}\n\n"
                        f"Leverage these insights to make an informed and strategic decision."
                    ),
                },
            ]
        else:
            # Debate ablation: no Bull/Bear debate, no Research Manager synthesis
            # -- the Trader is the ONLY LLM call that sees the analysts' reports
            # and has to form its own view directly from them, unmediated.
            messages = [
                {
                    "role": "system",
                    "content": (
                        _NO_POSITION_INSTRUCTION
                        + " No research debate or manager synthesis ran ahead of you for this "
                        "run -- you are reading the raw analyst reports directly and forming "
                        "your own view from them. "
                        + grounding
                        + NO_EXTERNAL_TOOLS
                        + get_language_instruction()
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Here are four analysts' reports for {company_name}. {instrument_context}\n\n"
                        f"{report_section}"
                        f"Market Report: {state.get('market_report', 'N/A')}\n\n"
                        f"Sentiment Report: {state.get('sentiment_report', 'N/A')}\n\n"
                        f"News Report: {state.get('news_report', 'N/A')}\n\n"
                        f"Fundamentals Report: {state.get('fundamentals_report', 'N/A')}"
                        f"{external_section}\n\n"
                        f"Weigh these directly and make an informed, strategic trading decision."
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

        result = {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
            "sender": name,
        }
        if not debate_enabled:
            # Portfolio Manager reads state["investment_plan"] unconditionally --
            # keep it populated with a clear sentinel rather than let a KeyError
            # surface deep in a downstream node for what is actually just an
            # intentionally-skipped step.
            result["investment_plan"] = _DEBATE_SKIPPED_PLACEHOLDER
        return result

    return functools.partial(trader_node, name="Trader")
