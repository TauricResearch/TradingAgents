"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import TraderProposal, render_trader_proposal
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.prompt_cache import (
    budgeted_dynamic_text,
    stable_join_sections,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.personas.prompt_overlay import apply_fragment


TRADER_SYSTEM_PROMPT = (
    "You are a trading agent analyzing market data to make investment decisions. "
    "Based on your analysis, provide a specific recommendation to buy, sell, or hold. "
    "Anchor your reasoning in the analysts' reports and the research plan."
)


def build_trader_user_prompt(state: dict) -> str:
    company_name = state["company_of_interest"]
    asset_type = state.get("asset_type", "stock")
    return stable_join_sections(
        [
            ("Instrument Context", build_instrument_context(company_name, asset_type)),
            (
                "Research Manager Investment Plan",
                budgeted_dynamic_text(
                    state.get("investment_plan", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "research manager investment plan",
                ),
            ),
            (
                "Reusable Prior Analysis Pack",
                budgeted_dynamic_text(
                    state.get("prior_analysis_pack_context", ""),
                    "prompt_cache_prior_pack_budget_chars",
                    8000,
                    "prior analysis pack",
                ),
            ),
            ("Current Task", "Produce the transaction proposal."),
        ]
    )


def create_trader(llm, persona=None):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state, name):
        system_prompt = apply_fragment(
            TRADER_SYSTEM_PROMPT + get_language_instruction(),
            persona,
        )
        user_prompt = build_trader_user_prompt(state)

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
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
